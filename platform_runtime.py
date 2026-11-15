"""Platform boundaries shared by source and frozen desktop distributions."""
import os
from pathlib import Path
import queue
import shlex
import shutil
import subprocess
import sys
import uuid

VERSION = '0.3.0-beta.6'
APP_NAME = 'Agentlings'


def state_directory():
    override = os.environ.get('AGENTLINGS_STATE_DIR') or os.environ.get('CODEX_FLOAT_STATE_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home()))
        current, legacy = base / APP_NAME, base / 'CodexFloat'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
        current, legacy = base / APP_NAME, base / 'CodexFloat'
    else:
        base = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
        current, legacy = base / 'agentlings', base / 'codex-float'
    # Share existing preferences and locks with older running versions. No copy,
    # move, or second independent monitor is introduced by the product rename.
    return legacy if legacy.is_dir() else current


def discovery_enabled():
    return os.environ.get('AGENTLINGS_DISABLE_DISCOVERY', os.environ.get('CODEX_FLOAT_DISABLE_DISCOVERY')) != '1'


def background_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}


def app_command(script='agentlings.py', *args, background=False):
    if getattr(sys, 'frozen', False):
        mode = ['terminal-session'] if script == 'terminal_session.py' else []
        return [sys.executable, *mode, *args]
    python = Path(sys.executable)
    if os.name == 'nt':
        python = python.with_name('pythonw.exe' if background else 'python.exe')
    return [str(python), str(Path(__file__).parent / script), *args]


def external_environment():
    env = os.environ.copy()
    if getattr(sys, 'frozen', False):
        for name in ('LD_LIBRARY_PATH', 'LIBPATH'):
            if name + '_ORIG' in env:
                env[name] = env[name + '_ORIG']
            else:
                env.pop(name, None)
    return env


def lock_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    handle.seek(0)
    handle.write(b'1')
    handle.flush()
    handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


class PortableWindows:
    """No fabricated foreground/tab identities on unsupported window managers."""
    def foreground(self): return None
    def inspect(self, _): return None
    def activate(self, _): return False
    def terminal_windows(self, _): return []
    def all_terminal_windows(self): return []


class PortableHotkeys:
    def __init__(self):
        self.events = queue.Queue()
        self.labels = {}
        self.error = None
    def close(self): pass


def capabilities(native=None, hotkeys=None):
    windows = os.name == 'nt'
    result = {'app': APP_NAME, 'platform': sys.platform, 'version': VERSION, 'terminal_tab_focus': windows,
            'automatic_docking': windows, 'global_hotkeys': windows,
            'desktop_mode': 'native' if windows else 'portable-beta'}
    if sys.platform == 'linux' and native is not None:
        import importlib.util
        from linux_desktop import bridge
        available = bridge().available
        result.update(window_focus=available, automatic_docking=available,
            terminal_tab_focus=available and importlib.util.find_spec('pyatspi') is not None,
            global_hotkeys=bool(hotkeys and hotkeys.labels),
            desktop_mode='gnome' if available else 'portable-beta',
            desktop_error=bridge().error)
    return result


def launch_terminal(command, cwd):
    """Pass argv directly on Linux; quote a private launcher for macOS Terminal."""
    env = external_environment()
    if sys.platform == 'darwin':
        folder = state_directory() / 'launchers'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / (uuid.uuid4().hex + '.command')
        # The script unlinks itself after Terminal has opened it. No prompt content.
        path.write_text('#!/bin/sh\nrm -f -- "$0"\ncd -- ' + shlex.quote(cwd) +
                        ' || exit 1\nexec ' + shlex.join(command) + '\n', encoding='utf-8')
        path.chmod(0o700)
        try:
            subprocess.run(['open', '-a', 'Terminal', str(path)], env=env, check=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as error:
            path.unlink(missing_ok=True)
            raise RuntimeError('No se pudo abrir Terminal.') from error
        return
    for name, flags in [('x-terminal-emulator', ['-e']), ('gnome-terminal', ['--']),
                        ('konsole', ['-e']), ('xfce4-terminal', ['--execute']), ('xterm', ['-e'])]:
        executable = shutil.which(name)
        if executable:
            return subprocess.Popen([executable, *flags, *command], cwd=cwd, env=env, start_new_session=True)
    raise RuntimeError('Instala una terminal compatible: xterm, GNOME Terminal, Konsole o XFCE Terminal.')


def open_text(path):
    command = ['notepad.exe', str(path)] if os.name == 'nt' else (['open', '-t', str(path)] if sys.platform == 'darwin'
                                                                    else ['xdg-open', str(path)])
    subprocess.Popen(command, env=external_environment())


class PortableAudio:
    def __init__(self):
        self.process = None

    def __call__(self, path):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired as error:
                    raise RuntimeError('Audio player did not stop') from error
            self.process = None
        if path is None:
            return
        candidates = ['afplay'] if sys.platform == 'darwin' else ['pw-play', 'paplay', 'aplay']
        executable = next((found for name in candidates if (found := shutil.which(name))), None)
        if not executable:
            raise RuntimeError('No supported audio player')
        self.process = subprocess.Popen([executable, str(path)], stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, env=external_environment())
