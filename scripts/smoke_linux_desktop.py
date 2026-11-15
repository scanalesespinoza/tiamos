"""Exercise real GNOME/Wayland windows on a private bus and virtual monitor.

Run as a desktop user with GNOME Shell, GNOME Terminal, dbus-run-session,
PyGObject, pyatspi, Tk and Pillow installed. No real agent/model is launched.
The test never injects input into the user's session or changes its settings.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def until(check, message, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.15)
    raise AssertionError(message)


def inside(folder):
    from gi.repository import Gio, GLib
    from linux_desktop import DesktopBridge, LinuxWindows, bridge
    from linux_tabs import tabs, select_tab, window_tabs
    from window_focus import dock_position
    folder = Path(folder)
    log = (folder/'desktop.log').open('w')
    processes = []
    def spawn(command):
        process = subprocess.Popen(command, stdout=log, stderr=log)
        processes.append(process)
        return process
    def run(command):
        return subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    app = [sys.executable, str(ROOT/'agentlings.py')]
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    def call(dest, path, iface, method, signature=None, values=()):
        return connection.call_sync(dest, path, iface, method,
            GLib.Variant(signature, values) if signature else None, None, 0, 2000, None).unpack()
    try:
        run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', "['agentlings@agentlings.local']"])
        # Start accessibility helpers explicitly on the private bus. Some distro
        # D-Bus activation policies only support the normal systemd user bus.
        spawn(['/usr/libexec/at-spi-bus-launcher', '--launch-immediately'])
        until(lambda: connection.get_unique_name(), 'No test bus')
        time.sleep(.3)
        spawn(['/usr/libexec/at-spi2-registryd'])
        shell = spawn(['gnome-shell', '--headless', '--wayland', '--virtual-monitor', '1280x900',
                       '--wayland-display', 'agentlings-test'])
        desktop = bridge()
        until(lambda: desktop.refresh(force=True).get('version') == 1, 'GNOME bridge did not load')
        assert shell.poll() is None
        os.environ['WAYLAND_DISPLAY'] = 'agentlings-test'
        os.environ['GDK_BACKEND'] = 'wayland'
        # Tk uses the private compositor's XWayland server, not the host display.
        match = until(lambda: re.search(r'Using public X11 display (:\d+)', (folder/'desktop.log').read_text()),
                      'No test XWayland display')
        os.environ['DISPLAY'] = match.group(1)
        auth = until(lambda: next((folder/'runtime').glob('.mutter-Xwaylandauth.*'), None), 'No test Xauthority')
        os.environ['XAUTHORITY'] = str(auth)
        spawn(['/usr/libexec/gnome-terminal-server'])
        until(lambda: call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'NameHasOwner', '(s)', ('org.gnome.Terminal',))[0], 'Terminal server did not start')
        run(['gnome-terminal', '--window', '--title=Agentlings smoke A', '--command=sleep 180',
             '--tab', '--title=Agentlings smoke B', '--command=sleep 180'])
        native = LinuxWindows()
        window = until(lambda: next(iter(native.all_terminal_windows()), None), 'No terminal window')
        records = until(lambda: (rows if len(rows := window_tabs(native.inspect(window.hwnd), tabs(force=True))) == 2 else None),
                        'Expected two real accessible tabs')
        assert {row['title'] for row in records} == {'Agentlings smoke A', 'Agentlings smoke B'}
        for record in records:
            select_tab(dict(hwnd=window.hwnd, window_pid=window.pid, tab_id=record['id']))
            until(lambda: desktop.refresh(force=True).get('foreground') == window.hwnd, 'Terminal did not focus')
            until(lambda: any(t['id'] == record['id'] and t['selected'] for t in tabs(force=True)), 'Wrong tab selected')
        # Native synthetic input is confined to this private compositor session.
        remote = 'org.gnome.Mutter.RemoteDesktop'
        session = call(remote, '/org/gnome/Mutter/RemoteDesktop', remote, 'CreateSession')[0]
        iface = remote + '.Session'
        call(remote, session, iface, 'Start')
        def keys(symbols):
            for symbol in symbols:
                call(remote, session, iface, 'NotifyKeyboardKeysym', '(ub)', (symbol, True))
            for symbol in reversed(symbols):
                call(remote, session, iface, 'NotifyKeyboardKeysym', '(ub)', (symbol, False))
        # Super+H minimizes an actual Wayland terminal, Activate restores it.
        keys([0xffeb, ord('h')])
        until(lambda: (desktop.refresh(force=True), native.inspect(window.hwnd).minimized)[1], 'Minimize not observed')
        assert native.activate(window)
        until(lambda: (desktop.refresh(force=True), not native.inspect(window.hwnd).minimized)[1], 'Restore failed')
        # Start a real monitor with two synthetic sessions and actual terminal bindings.
        codex, state = folder/'codex', folder/'state'
        codex.mkdir(); state.mkdir(); (state/'cli-sessions').mkdir()
        stamp = dt.datetime.now(dt.timezone.utc)
        connection_db = sqlite3.connect(codex/'state_5.sqlite')
        connection_db.execute('CREATE TABLE threads (id,title,cwd,rollout_path,source,archived,updated_at,attached_thread_parent_id)')
        identities = []
        for index, record in enumerate(records):
            ident = f'11111111-2222-4333-8444-{index:012d}'
            identities.append(ident)
            trace = codex/f'{ident}.jsonl'
            trace.write_text(json.dumps({'timestamp': stamp.isoformat(), 'type': 'event_msg',
                'payload': {'type': 'task_started', 'turn_id': 'local-smoke'}})+'\n')
            connection_db.execute('INSERT INTO threads VALUES (?,?,?,?,?,0,?,NULL)',
                (ident, record['title'], str(folder), str(trace), 'cli', stamp.timestamp()))
            (state/'cli-sessions'/f'{ident}.json').write_text(json.dumps({'id': ident, 'running': True,
                'heartbeat': time.time()+120, 'started_at': stamp.timestamp(), 'kind': 'tab',
                'hwnd': window.hwnd, 'window_pid': window.pid, 'tab_id': record['id'], 'selected': record['selected']}))
        connection_db.commit(); connection_db.close()
        os.environ.update(CODEX_HOME=str(codex), CLAUDE_CONFIG_DIR=str(folder/'claude'), AGENTLINGS_STATE_DIR=str(state))
        run([*app, 'on'])
        def status():
            return json.loads(run([*app, 'status']).stdout)
        data = until(lambda: (s if (s := status()).get('chats') == 2 and len(s.get('hotkeys', {})) == 2 else None),
                     'Monitor did not discover sessions/register shortcuts')
        assert data['capabilities']['desktop_mode'] == 'gnome'
        for index, record in enumerate(records):
            select_tab(dict(hwnd=window.hwnd, window_pid=window.pid, tab_id=record['id']))
            until(lambda: status().get('selected') == identities[index], 'Avatar selection did not follow the tab')
            data = status()
            assert data['sizes'][identities[index]] == [178, 152]
            assert data['sizes'][identities[1-index]] == [89, 76]
        # Use the advertised bindings, including the conflict fallback group.
        keysyms = {'Super': 0xffeb, 'Ctrl': 0xffe3, 'Alt': 0xffe9, 'Shift': 0xffe1,
                   'Page_Up': 0xff55, 'Page_Down': 0xff56}
        def shortcut(action):
            keys([keysyms[part] for part in data['hotkeys'][action].split('+')])
        assert data['hotkeys'] == {'cycle_next': 'Ctrl+Alt+Page_Down', 'cycle_previous': 'Ctrl+Alt+Page_Up'}
        for action, modes in [('cycle_next', ('left', 'bottom', 'top')),
                              ('cycle_previous', ('bottom', 'left', 'top'))]:
            for mode in modes:
                shortcut(action)
                until(lambda: status().get('layout') == mode, 'Placement cycle failed: '+mode)
                if mode == 'bottom':
                    placed = status()
                    bottom = placed['layout_area'][3]
                    assert all(placed['windows'][ident][1]+placed['sizes'][ident][1] == bottom-12
                               for ident in identities), 'Bottom layout is not aligned with work area'
        # Double-click the active avatar with XTest on the isolated XWayland display.
        import ctypes
        x11, xtst = ctypes.CDLL('libX11.so.6'), ctypes.CDLL('libXtst.so.6')
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        display = x11.XOpenDisplay(None)
        assert display
        try:
            data = status()
            active = data['selected']
            x, y = data['windows'][active]
            xtst.XTestFakeMotionEvent(display, -1, x+40, y+50, 0)
            for _ in range(2):
                xtst.XTestFakeButtonEvent(display, 1, 1, 0)
                xtst.XTestFakeButtonEvent(display, 1, 0, 0)
                x11.XFlush(display)
                time.sleep(.08)
        finally:
            x11.XCloseDisplay(display)
        data = until(lambda: (s if (s := status()).get('docked', {}).get(active) else None), 'Double-click did not dock avatar')
        desktop.refresh(force=True)
        expected = dock_position(native.inspect(window.hwnd).client)
        assert data['windows'][active] == list(expected), (data['windows'][active], expected)
        # Real GNOME maximization changes the geometry observed by the avatar.
        keys([0xffe9, 0xffc7])  # Alt+F10
        previous = expected
        until(lambda: (desktop.refresh(force=True), dock_position(native.inspect(window.hwnd).client) != previous)[1],
              'Window geometry did not change')
        until(lambda: status()['windows'][active] == list(dock_position(native.inspect(window.hwnd).client)),
              'Avatar did not follow window geometry')
        run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', '[]'])
        until(lambda: status().get('capabilities', {}).get('desktop_mode') == 'portable-beta',
              'Unavailable extension left stale capability claims')
        run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', "['agentlings@agentlings.local']"])
        until(lambda: status().get('capabilities', {}).get('desktop_mode') == 'gnome' and len(status().get('hotkeys', {})) == 2,
              'Monitor did not recover its desktop integration')
        run([*app, 'off'])
        owner = DesktopBridge(); owner.want_shortcuts = True
        assert len(owner.refresh(force=True)['labels']) == 2, 'Shortcuts not released on shutdown'
        owner.close()
        crash = subprocess.Popen([sys.executable, '-c',
            'import time; from linux_desktop import DesktopBridge; b=DesktopBridge(); '
            'b.want_shortcuts=True; print(len(b.refresh(force=True)["labels"]), flush=True); time.sleep(60)'],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=log, text=True)
        processes.append(crash)
        assert crash.stdout.readline().strip() == '2'
        crash.kill(); crash.wait(timeout=5); crash.stdout.close()
        replacement = DesktopBridge(); replacement.want_shortcuts = True
        until(lambda: len(replacement.refresh(force=True).get('labels', {})) == 2, 'Crash left shortcut reservations')
        replacement.close()
        call(remote, session, iface, 'Stop')
        print(json.dumps({'gnome_wayland': True, 'exact_tabs': True, 'focus_sizing': True,
            'minimize_restore': True, 'docking': True, 'follow_geometry': True,
            'global_shortcuts': True, 'shortcut_cleanup': True, 'crash_cleanup': True, 'reconnection': True}))
    finally:
        try:
            run([*app, 'off'])
        except Exception:
            pass
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
        log.close()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--inside':
        # Never permit a direct invocation to inject input into the user's bus.
        folder = Path(sys.argv[2])
        assert os.environ.get('XDG_RUNTIME_DIR') == str(folder/'runtime')
        assert os.environ.get('AGENTLINGS_PRIVATE_DESKTOP_TEST') == str(folder)
        inside(folder)
        return
    if os.getuid() == 0:
        raise SystemExit('Run as a desktop user, not root.')
    with tempfile.TemporaryDirectory(prefix='agentlings-desktop-test-') as tmp:
        folder = Path(tmp)
        for name in ('runtime', 'config', 'share'):
            (folder/name).mkdir(mode=0o700)
        shutil.copytree(ROOT/'linux/gnome-extension', folder/'share/gnome-shell/extensions/agentlings@agentlings.local')
        env = os.environ.copy()
        for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'AT_SPI_BUS_ADDRESS',
                     'AGENTLINGS_DISABLE_DISCOVERY', 'CODEX_FLOAT_DISABLE_DISCOVERY'):
            env.pop(name, None)
        env.update(XDG_RUNTIME_DIR=str(folder/'runtime'), XDG_CONFIG_HOME=str(folder/'config'),
            XDG_DATA_HOME=str(folder/'share'), GSETTINGS_BACKEND='keyfile', AGENTLINGS_DISABLE_ELEVATED_OBSERVER='1',
            XDG_CURRENT_DESKTOP='GNOME', LIBGL_ALWAYS_SOFTWARE='1', AGENTLINGS_PRIVATE_DESKTOP_TEST=str(folder))
        # No automatic service directories: tests must not start the operator's
        # online accounts, keyring, FUSE mounts or other desktop services.
        config = folder/'bus.conf'
        config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' + str(folder/'runtime') +
            '</listen><auth>EXTERNAL</auth><policy context="default"><allow own="*"/>'
            '<allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>')
        result = subprocess.run(['dbus-run-session', '--config-file', str(config), '--', sys.executable,
            __file__, '--inside', str(folder)], env=env, capture_output=True, text=True)
        if result.returncode:
            print(result.stderr[-4000:])
            print((folder/'desktop.log').read_text()[-3000:])
            raise SystemExit(result.returncode)
        print(result.stdout.strip())


if __name__ == '__main__':
    main()
