"""Window association and safe client-area docking for Windows companions."""
from dataclasses import dataclass
import os
from pathlib import PureWindowsPath


FULL_SIZE = (178, 152)
HALF_SIZE = (89, 76)


def avatar_size(ident, selected):
    return FULL_SIZE if selected is None or ident == selected else HALF_SIZE


def dock_position(client, size=FULL_SIZE, dpi=96):
    """Stay below custom title bars as well as standard non-client controls."""
    left, top, right, bottom = client
    margin = max(8, round(12 * dpi / 96))
    header = max(48, round(52 * dpi / 96))
    width, height = size
    if right - left < width + 2 * margin or bottom - top < height + header + margin:
        return None
    return right - width - margin, top + header


@dataclass
class Window:
    hwnd: int
    pid: int
    executable: str
    title: str
    client: tuple
    visible: bool
    minimized: bool
    dpi: int = 96

    @property
    def terminal(self):
        return PureWindowsPath(self.executable).name.lower() in {'windowsterminal.exe', 'openconsole.exe', 'conhost.exe', 'powershell.exe', 'pwsh.exe', 'cmd.exe'}


def foreground_selection(bindings, foreground, selected):
    """Highlight only an eligible CLI session in the foreground window."""
    matches = [ident for ident, hwnd in bindings.items() if hwnd == foreground]
    if selected in matches:
        return selected
    return matches[0] if len(matches) == 1 else None


class Windows:
    def __init__(self):
        import ctypes as C
        from ctypes import wintypes as W
        self.C, self.W = C, W
        self.u = C.WinDLL('user32', use_last_error=True)
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.u.EnumWindows.argtypes = [self.callback_type, W.LPARAM]
        self.u.GetForegroundWindow.restype = W.HWND
        for name in ('IsWindow', 'IsWindowVisible', 'IsIconic', 'SetForegroundWindow'):
            getattr(self.u, name).argtypes = [W.HWND]
        self.u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        self.u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.u.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
        self.u.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
        self.u.ShowWindow.argtypes = [W.HWND, C.c_int]
        self.u.GetDpiForWindow.argtypes = [W.HWND]
        self.k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.k.OpenProcess.restype = W.HANDLE
        self.k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
        self.k.CloseHandle.argtypes = [W.HANDLE]

    def foreground(self):
        return self.u.GetForegroundWindow()

    def inspect(self, hwnd):
        C, W, u = self.C, self.W, self.u
        if not hwnd or not u.IsWindow(hwnd):
            return None
        pid = W.DWORD()
        u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value == os.getpid():
            return None
        title = C.create_unicode_buffer(2048)
        u.GetWindowTextW(hwnd, title, len(title))
        if not title.value or 'is using your computer' in title.value:
            return None
        process = self.k.OpenProcess(0x1000, False, pid.value)
        if not process:
            return None
        try:
            path = C.create_unicode_buffer(32768)
            length = W.DWORD(len(path))
            if not self.k.QueryFullProcessImageNameW(process, 0, path, C.byref(length)):
                return None
        finally:
            self.k.CloseHandle(process)
        rect, origin = W.RECT(), W.POINT(0, 0)
        if not u.GetClientRect(hwnd, C.byref(rect)) or not u.ClientToScreen(hwnd, C.byref(origin)):
            return None
        return Window(hwnd, pid.value, path.value, title.value,
                      (origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom),
                      bool(u.IsWindowVisible(hwnd)), bool(u.IsIconic(hwnd)), u.GetDpiForWindow(hwnd) or 96)

    def terminal_windows(self, token):
        result = []

        @self.callback_type
        def collect(hwnd, _):
            # Avoid opening handles to unrelated processes while polling.
            title = self.C.create_unicode_buffer(256)
            self.u.GetWindowTextW(hwnd, title, len(title))
            if f'Codex CLI [{token}]' in title.value:
                window = self.inspect(hwnd)
                if window and window.terminal:
                    result.append(window)
            return True

        self.u.EnumWindows(collect, 0)
        return result

    def all_terminal_windows(self):
        result = []

        @self.callback_type
        def collect(hwnd, _):
            if self.u.IsWindowVisible(hwnd):
                window = self.inspect(hwnd)
                if window and window.terminal:
                    result.append(window)
            return True

        self.u.EnumWindows(collect, 0)
        return result

    def activate(self, window):
        if not window.visible or window.minimized:
            self.u.ShowWindow(window.hwnd, 9)  # SW_RESTORE
        return bool(self.u.SetForegroundWindow(window.hwnd))
