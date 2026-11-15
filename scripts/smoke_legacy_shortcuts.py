"""Exercise v1 live-session shortcut compatibility on a private bus/settings."""
import os
from pathlib import Path
import queue
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def inside():
    from gi.repository import Gio
    from linux_legacy_shortcuts import LegacyShortcuts, clear_owned, SCHEMA, PREFIX, ACTIONS
    parent = Gio.Settings.new(SCHEMA)
    other = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/unrelated-test/'
    parent.set_strv('custom-keybindings', [other])
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    events = queue.Queue()
    shortcuts = LegacyShortcuts(connection, events)
    try:
        for action in ACTIONS:
            setting = Gio.Settings.new_with_path(SCHEMA+'.custom-keybinding', PREFIX+action+'/')
            subprocess.run(shlex.split(setting.get_string('command')), check=True, timeout=5)
            deadline = time.monotonic()+3
            while events.empty() and time.monotonic() < deadline:
                shortcuts.poll(); time.sleep(.02)
            assert events.get_nowait() == action
        assert other in parent.get_strv('custom-keybindings')
    finally:
        shortcuts.close()
    assert parent.get_strv('custom-keybindings') == [other]
    # Startup cleanup also removes bindings left without a live receiver.
    stale = Gio.Settings.new_with_path(SCHEMA+'.custom-keybinding', PREFIX+'cycle_next/')
    stale.set_string('name', 'tiamos cycle_next')
    parent.set_strv('custom-keybindings', [other, PREFIX+'cycle_next/'])
    clear_owned()
    assert parent.get_strv('custom-keybindings') == [other]
    print('PASS two placement signals, unrelated shortcuts preserved, shutdown and stale-binding cleanup')


if __name__ == '__main__':
    if sys.argv[1:] == ['--inside']:
        assert os.environ.get('GSETTINGS_BACKEND') == 'memory'
        inside()
    else:
        subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--inside'],
            env=dict(os.environ, GSETTINGS_BACKEND='memory'), check=True)
