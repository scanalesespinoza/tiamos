"""Install the source desktop for the current user, without changing other apps."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
UUID = 'agentlings@agentlings.local'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gnome-extension', action='store_true')
    parser.add_argument('--kitty', action='store_true', help='Install private Kitty focus integration')
    parser.add_argument('--autostart', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.getuid() == 0:
        parser.error('Run as your desktop user on Linux, without sudo.')
    import tkinter  # Check the installed interpreter, including its Tk support.
    import PIL.ImageTk
    import psutil
    if args.gnome_extension:
        import gi
        import pyatspi
    home = Path.home()
    app = home / '.local/share/tiamos/app'
    app.mkdir(parents=True, exist_ok=True)
    for source in ROOT.glob('*.py'):
        if not source.name.startswith('test_'):
            shutil.copy2(source, app / source.name)
    if args.kitty:
        kitty = home / '.config/kitty'
        kitty.mkdir(parents=True, exist_ok=True)
        fragment = kitty/'tiamos.conf'
        fragment.write_text(f'watcher {app}/kitty_watcher.py\nmap ctrl+alt+shift+f12 remote_control_script {app}/kitty_bridge.py\n')
        config = kitty/'kitty.conf'
        content = config.read_text() if config.exists() else ''
        content = content.replace('include agentlings.conf', 'include tiamos.conf').replace('# Agentlings local pane focus bridge', '# tiamos local pane focus bridge')
        if 'include tiamos.conf' not in content.splitlines():
            content += '\n# tiamos local pane focus bridge\ninclude tiamos.conf\n'
        config.write_text(content)
    launcher = home / '.local/bin/tiamos'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(app/'tiamos.py')]) + ' "$@"\n')
    launcher.chmod(0o755)
    for name in ('agentlings', 'codex-float'):
        alias = launcher.with_name(name)
        if alias.is_symlink() and alias.readlink().name in ('agentlings', 'tiamos'):
            alias.unlink()
        elif alias.is_file():
            old = alias.read_text()
            if '/agentlings/app/agentlings.py' in old or '/tiamos/app/tiamos.py' in old:
                alias.unlink()
            else:
                raise SystemExit(f'Preserving unrelated launcher: {alias}')
        if not alias.exists():
            alias.symlink_to('tiamos')
    desktop_command = '"' + str(launcher).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
    desktop = ('[Desktop Entry]\nType=Application\nName=tiamos\n'
               f'Exec={desktop_command} on\n'
               'Icon=face-smile\nTerminal=false\nCategories=Development;\n')
    entry = home / '.local/share/applications/tiamos.desktop'
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(desktop)
    old_autostart = home / '.config/autostart/agentlings.desktop'
    preserve_autostart = old_autostart.exists() and 'Name=Agentlings' in old_autostart.read_text()
    if args.autostart or preserve_autostart:
        entry = home / '.config/autostart/tiamos.desktop'
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(desktop)
    for old in (home/'.local/share/applications/agentlings.desktop', old_autostart):
        if old.is_file() and 'Name=Agentlings' in old.read_text():
            old.unlink()
    if args.gnome_extension:
        from gi.repository import Gio
        destination = home / '.local/share/gnome-shell/extensions' / UUID
        shutil.copytree(ROOT/'linux/gnome-extension', destination, dirs_exist_ok=True)
        settings = Gio.Settings.new('org.gnome.shell')
        enabled = settings.get_strv('enabled-extensions')
        if UUID not in enabled:
            if not settings.set_strv('enabled-extensions', [*enabled, UUID]):
                raise SystemExit('GNOME extension settings are not writable.')
        Gio.Settings.sync()
        print('GNOME extension installed; new code loads at the next desktop login. Existing v1 placement shortcuts update without logout.')
    print(f'Installed: {launcher}\nStart with: tiamos on')


if __name__ == '__main__':
    main()
