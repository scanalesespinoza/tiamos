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
    app = home / '.local/share/agentlings/app'
    app.mkdir(parents=True, exist_ok=True)
    for source in ROOT.glob('*.py'):
        if not source.name.startswith('test_'):
            shutil.copy2(source, app / source.name)
    launcher = home / '.local/bin/agentlings'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(app/'agentlings.py')]) + ' "$@"\n')
    launcher.chmod(0o755)
    alias = launcher.with_name('codex-float')
    if not alias.exists() and not alias.is_symlink():
        alias.symlink_to('agentlings')
    desktop_command = '"' + str(launcher).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
    desktop = ('[Desktop Entry]\nType=Application\nName=Agentlings\n'
               f'Exec={desktop_command} on\n'
               'Icon=face-smile\nTerminal=false\nCategories=Development;\n')
    entry = home / '.local/share/applications/agentlings.desktop'
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(desktop)
    if args.autostart:
        entry = home / '.config/autostart/agentlings.desktop'
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(desktop)
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
        print('GNOME extension installed. Log out and back in to load new extension code.')
    print(f'Installed: {launcher}\nStart with: agentlings on')


if __name__ == '__main__':
    main()
