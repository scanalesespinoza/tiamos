import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const IFACE = `<node><interface name="org.agentlings.Desktop1">
<method name="Snapshot"><arg type="s" direction="out"/></method>
<method name="Activate"><arg type="u" direction="in"/><arg type="u" direction="in"/><arg type="b" direction="out"/></method>
<method name="Attach"><arg type="s" direction="out"/></method>
<method name="Detach"/>
</interface></node>`;
const KEYS = [['top', 'Up'], ['right', 'Right'], ['left', 'Left'], ['toggle_visibility', 'Down']];
const TERMINALS = new Set(['org.gnome.Terminal', 'org.gnome.Ptyxis', 'org.gnome.Console',
    'org.kde.konsole', 'kitty', 'Alacritty', 'com.mitchellh.ghostty', 'xfce4-terminal', 'xterm']);

export default class Agentlings extends Extension {
    enable() {
        this._owner = null;
        this._watch = 0;
        this._held = new Map();
        this._events = [];
        this._labels = {};
        this._error = null;
        this._object = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._object.export(Gio.DBus.session, '/org/agentlings/Desktop');
        this._name = Gio.bus_own_name_on_connection(Gio.DBus.session, 'org.agentlings.Desktop',
            Gio.BusNameOwnerFlags.NONE, null, null);
        this._signal = global.display.connect('accelerator-activated', (_display, action) => {
            if (this._held.has(action) && this._events.length < 32)
                this._events.push(this._held.get(action));
        });
    }

    _terminals() {
        const tracker = Shell.WindowTracker.get_default();
        return global.get_window_actors().map(actor => actor.meta_window).filter(window => {
            const app = tracker.get_window_app(window)?.get_id()?.replace(/\.desktop$/, '');
            return TERMINALS.has(app) || TERMINALS.has(window.get_wm_class());
        }).slice(0, 128);
    }

    SnapshotAsync(_args, invocation) {
        // Only terminal metadata is exposed. No terminal contents or arbitrary Shell evaluation.
        const focused = global.display.focus_window;
        const windows = this._terminals().map(window => {
            const rect = window.get_frame_rect();
            return {id: window.get_stable_sequence(), pid: window.get_pid(),
                app: Shell.WindowTracker.get_default().get_window_app(window)?.get_id() ?? window.get_wm_class(),
                title: (window.get_title() ?? '').slice(0, 512),
                client: [rect.x, rect.y, rect.x + rect.width, rect.y + rect.height],
                minimized: window.minimized, visible: !window.is_hidden() || window.minimized,
                focused: window === focused};
        });
        const workspace = global.workspace_manager.get_active_workspace();
        const monitors = Main.layoutManager.monitors.map((_monitor, index) => {
            const rect = workspace.get_work_area_for_monitor(index);
            return [rect.x, rect.y, rect.x + rect.width, rect.y + rect.height];
        });
        const owner = invocation.get_sender() === this._owner;
        const data = {version: 1, windows, monitors, pointer: global.get_pointer().slice(0, 2),
            foreground: windows.find(w => w.focused)?.id ?? null,
            labels: owner ? this._labels : {}, error: owner ? this._error : null,
            events: owner ? this._events.splice(0) : []};
        invocation.return_value(new GLib.Variant('(s)', [JSON.stringify(data)]));
    }

    Activate(id, pid) {
        const window = this._terminals().find(w => w.get_stable_sequence() === id && w.get_pid() === pid);
        if (!window)
            return false;
        window.unminimize();
        Main.activateWindow(window, global.get_current_time());
        return true;
    }

    _release() {
        for (const action of this._held.keys()) {
            Main.wm.allowKeybinding(Meta.external_binding_name_for_action(action), Shell.ActionMode.NONE);
            global.display.ungrab_accelerator(action);
        }
        this._held.clear();
        this._events = [];
        this._labels = {};
    }

    AttachAsync(_args, invocation) {
        const sender = invocation.get_sender();
        if (this._owner && this._owner !== sender) {
            invocation.return_dbus_error('org.agentlings.Busy', 'Another Agentlings monitor owns the shortcuts.');
            return;
        }
        if (!this._owner) {
            this._owner = sender;
            this._watch = Gio.bus_watch_name_on_connection(Gio.DBus.session, sender,
                Gio.BusNameWatcherFlags.NONE, null, () => this._detach());
        }
        this._release();
        const groups = [
            ['<Control><Alt>', 'Ctrl+Alt'],
            ['<Control><Alt><Shift>', 'Ctrl+Alt+Shift'],
            ['<Super><Control><Alt>', 'Super+Ctrl+Alt'],
        ];
        for (const [modifiers, label] of groups) {
            for (const [name, key] of KEYS) {
                const accelerator = `${modifiers}${key}`;
                const action = global.display.grab_accelerator(accelerator, Meta.KeyBindingFlags.NONE);
                if (action === 0)
                    break;
                this._held.set(action, name);
                Main.wm.allowKeybinding(Meta.external_binding_name_for_action(action), Shell.ActionMode.NORMAL);
                this._labels[name] = `${label}+${key}`;
            }
            if (this._held.size === KEYS.length)
                break;
            this._release();
        }
        this._error = this._held.size ? null : 'Atajos ocupados; utiliza el menú de Agentlings.';
        invocation.return_value(new GLib.Variant('(s)', [JSON.stringify({labels: this._labels, error: this._error})]));
    }

    _detach() {
        this._release();
        if (this._watch)
            Gio.bus_unwatch_name(this._watch);
        this._watch = 0;
        this._owner = null;
    }

    DetachAsync(_args, invocation) {
        if (invocation.get_sender() === this._owner)
            this._detach();
        invocation.return_value(null);
    }

    disable() {
        this._detach();
        global.display.disconnect(this._signal);
        this._object.unexport();
        Gio.bus_unown_name(this._name);
    }
}
