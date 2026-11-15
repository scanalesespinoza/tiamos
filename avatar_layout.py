"""Group placement and collision-aware native desktop shortcuts."""
import ctypes as C
from ctypes import wintypes as W
import queue
import threading
import os
import sys
from itertools import chain


class _MonitorInfo(C.Structure):
    _fields_ = [('size', W.DWORD), ('monitor', W.RECT), ('work', W.RECT), ('flags', W.DWORD)]


def place_companion(entry, x, y):
    """Keep the requested position available before Tk commits window geometry."""
    entry['position'] = (x, y)
    width, height = entry['size']
    geometry = f'{width}x{height}{x:+d}{y:+d}'
    if geometry != entry.get('geometry'):
        entry['window'].geometry(geometry)
        entry['geometry'] = geometry


def arrange(items, area, anchor='top', margin=12, gap=12):
    """Pack variable-size companions into centered rows or edge columns."""
    left, top, right, bottom = area
    horizontal = anchor == 'top'
    available = (right - left if horizontal else bottom - top) - 2 * margin
    lines = []
    current = []
    used = 0
    for ident, width, height in items:
        extent = width if horizontal else height
        if current and used + gap + extent > available:
            lines.append(current)
            current, used = [], 0
        used += (gap if current else 0) + extent
        current.append((ident, width, height))
    if current:
        lines.append(current)
    positions = {}
    cross = top + margin if horizontal else right - margin if anchor == 'right' else left + margin
    for line in lines:
        length = sum(item[1 if horizontal else 2] for item in line) + gap * (len(line) - 1)
        along = (left + (right - left - length) // 2) if horizontal else (top + (bottom - top - length) // 2)
        thickness = max(item[2 if horizontal else 1] for item in line)
        for ident, width, height in line:
            x = along if horizontal else cross - width if anchor == 'right' else cross
            y = cross if horizontal else along
            positions[ident] = (x, y)
            along += (width if horizontal else height) + gap
        cross += thickness + gap if horizontal or anchor == 'left' else -(thickness + gap)
    return positions


KEYS = [('top', 0x26, 'Up'), ('right', 0x27, 'Right'), ('left', 0x25, 'Left'), ('toggle_visibility', 0x28, 'Down')]


def menu_after(rectangles, area, anchor='top', size=36, gap=12):
    """Attach the control to a manually placed group without covering a companion."""
    left, top, right, bottom = area
    x, y, width, height = rectangles[-1]
    trailing = (x + width + gap, y) if anchor == 'top' else (x + width - size if anchor == 'right' else x, y + height + gap)
    candidates = [trailing, (x - size - gap, y), (x, y - size - gap), (x + width + gap, y)]
    candidates = chain(candidates, ((cx, cy) for cy in range(top + gap, bottom - size, size + gap)
                                   for cx in range(left + gap, right - size, size + gap)))
    for cx, cy in candidates:
        cx, cy = max(left, min(cx, right - size)), max(top, min(cy, bottom - size))
        if all(not (cx < ox + ow and cx + size > ox and cy < oy + oh and cy + size > oy)
               for ox, oy, ow, oh in rectangles):
            return cx, cy
    return left, top


def register_available(register, unregister):
    for modifiers, label in [(0x4003, 'Ctrl+Alt'), (0x4007, 'Ctrl+Alt+Shift')]:
        held = []
        for index, (_, key, _) in enumerate(KEYS):
            ident = 0x7a10 + index
            if not register(ident, modifiers, key):
                break
            held.append(ident)
        if len(held) == len(KEYS):
            return held, {anchor: f'{label}+{name}' for anchor, _, name in KEYS}
        for ident in held:
            unregister(ident)
    return [], {}


class GlobalHotkeys:
    def __new__(cls):
        if sys.platform == 'linux':
            from linux_desktop import LinuxHotkeys
            return LinuxHotkeys()
        if os.name != 'nt':
            from platform_runtime import PortableHotkeys
            return PortableHotkeys()
        return super().__new__(cls)

    def __init__(self):
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.labels = {}
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        self.ready.wait(2)

    def run(self):
        import ctypes as C
        from ctypes import wintypes as W
        held = []
        user = C.WinDLL('user32', use_last_error=True)
        user.RegisterHotKey.argtypes = [W.HWND, C.c_int, W.UINT, W.UINT]
        user.UnregisterHotKey.argtypes = [W.HWND, C.c_int]
        user.PeekMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
        try:
            held, self.labels = register_available(
                lambda ident, modifiers, key: user.RegisterHotKey(None, ident, modifiers, key),
                lambda ident: user.UnregisterHotKey(None, ident))
            if not held:
                self.error = 'Atajos de flechas ocupados; utiliza el menú de los avatares.'
            self.ready.set()
            message = W.MSG()
            while not self.stop.wait(.03):
                while user.PeekMessageW(C.byref(message), None, 0x312, 0x312, 1):
                    index = int(message.wParam) - 0x7a10
                    if 0 <= index < len(KEYS):
                        self.events.put(KEYS[index][0])
        except Exception as error:
            self.error = f'No se pudieron registrar los atajos: {error}'
            self.ready.set()
        finally:
            for ident in held:
                user.UnregisterHotKey(None, ident)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)


def monitor_work_area(position=None):
    if sys.platform == 'linux':
        from linux_desktop import work_area
        area = work_area(position)
        if area:
            return area
    if os.name != 'nt':
        import tkinter as tk
        root = tk._default_root
        if root is None:
            raise RuntimeError('Desktop display is not initialized.')
        return (root.winfo_vrootx(), root.winfo_vrooty(),
                root.winfo_vrootx() + root.winfo_vrootwidth(), root.winfo_vrooty() + root.winfo_vrootheight())
    user = C.WinDLL('user32')
    user.MonitorFromPoint.argtypes = [W.POINT, W.DWORD]
    user.MonitorFromPoint.restype = W.HANDLE
    user.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(_MonitorInfo)]
    point = W.POINT()
    if position is None:
        user.GetCursorPos(C.byref(point))
    else:
        point.x, point.y = map(int, position)
    info = _MonitorInfo()
    info.size = C.sizeof(info)
    if not user.GetMonitorInfoW(user.MonitorFromPoint(point, 2), C.byref(info)):
        raise OSError('No se pudo consultar el area de trabajo del monitor.')
    return info.work.left, info.work.top, info.work.right, info.work.bottom
