"""Optional GNOME integration for both Wayland and X11.

The compositor extension exposes terminal metadata only. Missing dependencies or
an unavailable extension leave the portable desktop working, without invented
focus, geometry or shortcuts. No subprocess is spawned by the UI polling loop.
"""
import json
import os
import queue
import time
import threading

from platform_runtime import PortableWindows

SERVICE = 'org.agentlings.Desktop'
OBJECT = '/org/agentlings/Desktop'
INTERFACE = 'org.agentlings.Desktop1'


class DesktopBridge:
    def __init__(self):
        self.data = {}
        self.error = None
        self.available = False
        self.events = queue.Queue()
        self.labels = {}
        self.attached = False
        self.want_shortcuts = False
        self.next_poll = 0
        self.connection = None

    def call(self, method, signature=None, args=()):
        from gi.repository import Gio, GLib
        if self.connection is None:
            # A private connection makes shortcut ownership and cleanup per monitor.
            address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
            self.connection = Gio.DBusConnection.new_for_address_sync(address,
                Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                None, None)
        result = self.connection.call_sync(SERVICE, OBJECT, INTERFACE, method,
            GLib.Variant(signature, args) if signature else None, None,
            Gio.DBusCallFlags.NO_AUTO_START, 250, None)
        return result.unpack()

    def refresh(self, force=False):
        if not force and time.monotonic() < self.next_poll:
            return self.data
        self.next_poll = time.monotonic() + .1
        try:
            data = json.loads(self.call('Snapshot')[0])
            if data.get('version') != 1:
                raise ValueError('Unsupported desktop protocol')
            if self.want_shortcuts and not self.attached:
                attached = json.loads(self.call('Attach')[0])
                self.labels = attached['labels']
                self.attached = True
                data.update(attached)
            elif self.attached:
                self.labels = data.get('labels', {})
            for event in data.get('events', []):
                if event in ('top', 'left', 'right', 'toggle_visibility'):
                    self.events.put(event)
            self.data, self.available, self.error = data, True, data.get('error')
        except Exception:
            # A compositor restart invalidates all window IDs and shortcut claims.
            self.data, self.available, self.attached, self.labels = {}, False, False, {}
            self.error = 'Integración GNOME no disponible; instala y activa la extensión de Agentlings.'
            self.next_poll = time.monotonic() + 3
        return self.data

    def close(self):
        if self.attached:
            try:
                self.call('Detach')
            except Exception:
                pass
        if self.connection:
            self.connection.close_sync(None)
        self.connection = None
        self.available = self.attached = self.want_shortcuts = False
        self.labels = {}


_bridges = threading.local()


def bridge():
    if not hasattr(_bridges, 'value'):
        _bridges.value = DesktopBridge()
    return _bridges.value


def work_area(position=None):
    data = bridge().refresh()
    point = position or data.get('pointer')
    areas = data.get('monitors', [])
    if point and areas:
        x, y = point
        return tuple(min(areas, key=lambda r: max(r[0]-x, 0, x-r[2])**2 + max(r[1]-y, 0, y-r[3])**2))
    return None


class LinuxWindows(PortableWindows):
    def foreground(self):
        return bridge().refresh().get('foreground')

    def inspect(self, ident):
        if not ident:
            return None
        from window_focus import Window
        for record in bridge().refresh().get('windows', []):
            if record['id'] == ident and record['pid'] != os.getpid():
                return Window(record['id'], record['pid'], record['app'], record['title'],
                    tuple(record['client']), record['visible'], record['minimized'])
        return None

    def all_terminal_windows(self):
        return [window for row in bridge().refresh().get('windows', [])
                if (window := self.inspect(row['id'])) is not None]

    def terminal_windows(self, token):
        return [window for window in self.all_terminal_windows() if f'Codex CLI [{token}]' in window.title]

    def activate(self, window):
        bridge().refresh(force=True)
        current = self.inspect(window.hwnd)
        if not current or (current.pid, current.executable) != (window.pid, window.executable):
            return False
        try:
            return bool(bridge().call('Activate', '(uu)', (window.hwnd, window.pid))[0])
        except Exception:
            return False


class LinuxHotkeys:
    def __init__(self):
        self.bridge = bridge()
        self.events = self.bridge.events
        # Synthetic monitors must never reserve the real user's shortcuts.
        from platform_runtime import discovery_enabled
        self.bridge.want_shortcuts = discovery_enabled()
        self.bridge.refresh(force=True)

    @property
    def labels(self):
        return self.bridge.labels

    @property
    def error(self):
        return self.bridge.error

    def poll(self):
        self.bridge.refresh()

    def close(self):
        self.bridge.close()
