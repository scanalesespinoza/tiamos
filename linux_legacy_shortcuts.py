"""Live-session compatibility for the already loaded v1 GNOME extension.

GNOME cannot reload an imported extension. Its standard custom shortcuts send
only placement signals until v2 is loaded at the next desktop login. Only our
own two named settings are changed; close removes them, and startup cleans up
reservations left by a crashed monitor before native v2 grabs the same keys.
"""
import shlex
import shutil

ACTIONS = {'cycle_next': 'Page_Down', 'cycle_previous': 'Page_Up'}
SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys'
PREFIX = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/agentlings-'
INTERFACE = 'org.agentlings.Placement'
OBJECT = '/org/agentlings/Placement'


def clear_owned():
    from gi.repository import Gio
    if Gio.SettingsSchemaSource.get_default().lookup(SCHEMA, True) is None:
        return
    parent = Gio.Settings.new(SCHEMA)
    paths = list(parent.get_strv('custom-keybindings'))
    for action in ACTIONS:
        path = PREFIX + action + '/'
        setting = Gio.Settings.new_with_path(SCHEMA+'.custom-keybinding', path)
        if setting.get_string('name') in ('tiamos '+action, 'Agentlings '+action):
            paths = [p for p in paths if p != path]
            for key in ('binding', 'command', 'name'): setting.reset(key)
    parent.set_strv('custom-keybindings', paths)
    Gio.Settings.sync()


class LegacyShortcuts:
    def __init__(self, connection, events):
        from gi.repository import Gio
        self.connection = connection
        self.subscription = 0
        self.labels = {}
        self.error = None
        executable = shutil.which('gdbus')
        if not executable: raise RuntimeError('No se encuentra gdbus para activar los atajos de GNOME.')
        def signal(_connection, _sender, _path, _interface, _signal, parameters):
            values = parameters.unpack()
            if len(values) == 1 and values[0] in ACTIONS:
                events.put(values[0])
        self.subscription = connection.signal_subscribe(None, INTERFACE, 'Cycle', OBJECT,
            None, Gio.DBusSignalFlags.NONE, signal)
        try:
            parent = Gio.Settings.new(SCHEMA)
            paths = list(parent.get_strv('custom-keybindings'))
            for action, key in ACTIONS.items():
                path = PREFIX+action+'/'
                setting = Gio.Settings.new_with_path(SCHEMA+'.custom-keybinding', path)
                if setting.get_string('name') not in ('', 'tiamos '+action, 'Agentlings '+action):
                    raise RuntimeError('La ruta de atajos de tiamos pertenece a otra configuración.')
                command = shlex.join([executable, 'emit', '--session', '--object-path', OBJECT,
                    '--signal', INTERFACE+'.Cycle', "'"+action+"'"])
                for name, value in [('name', 'tiamos '+action), ('command', command),
                                    ('binding', '<Control><Alt>'+key)]:
                    if not setting.set_string(name, value):
                        raise RuntimeError('GNOME no permitió configurar los atajos de ubicación.')
                if path not in paths: paths.append(path)
                self.labels[action] = 'Ctrl+Alt+'+key
            if not parent.set_strv('custom-keybindings', paths):
                raise RuntimeError('GNOME no permitió activar los atajos de ubicación.')
            Gio.Settings.sync()
        except Exception:
            self.close()
            raise

    def poll(self):
        from gi.repository import GLib
        context = GLib.MainContext.default()
        for _ in range(16):
            if not context.pending(): break
            context.iteration(False)

    def close(self):
        clear_owned()
        if self.subscription:
            self.connection.signal_unsubscribe(self.subscription)
            self.subscription = 0
        self.labels = {}
