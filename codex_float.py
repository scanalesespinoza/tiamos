"""Small draggable Windows companions for today's local Codex conversations."""
from __future__ import annotations
import argparse
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import threading
import time
from window_focus import Windows, FULL_SIZE, HALF_SIZE, avatar_size, dock_position, foreground_selection
from cli_sessions import registrations, create_session, launch, thread_info
from avatar_layout import arrange, GlobalHotkeys, monitor_work_area
from session_activity import Activity, safe_preview
from avatar_theme import DEFAULTS, ThemeSettings, palettes, read_config, write_config

BASE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'CodexFloat'
CODEX = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def running():
    status = load_json(STATE / 'status.json', {})
    return status if time.time() - status.get('heartbeat', 0) < 8 else None


class Trace:
    """Incrementally inspect lifecycle and bounded, sanitized activity metadata."""
    END_EVENTS = {'task_complete', 'task_completed', 'turn_aborted', 'task_aborted', 'task_interrupted', 'turn_cancelled', 'session_end'}

    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0
        self.pending = b''
        self.active = set()
        self.last_activity = None
        self.activity = Activity()

    def read(self):
        if self.path.stat().st_size < self.offset:
            self.offset, self.pending = 0, b''
            self.active.clear()
            self.last_activity = None
            self.activity = Activity()
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            content = self.pending + stream.read()
            self.offset = stream.tell()
        lines = content.split(b'\n')
        self.pending = lines.pop()
        for line in lines:
            try:
                item = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(item, dict) or not isinstance(item.get('payload'), dict):
                continue
            payload = item.get('payload', {})
            kind = payload.get('type')
            try:
                stamp = dt.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')).astimezone()
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            self.activity.observe(item, stamp)
            if item.get('type') != 'event_msg' or kind not in {'task_started', 'user_message'} | self.END_EVENTS:
                continue
            if self.last_activity is None or stamp > self.last_activity:
                self.last_activity = stamp
            turn = payload.get('turn_id') or payload.get('task_id')
            if kind == 'task_started':
                self.active.add(turn or 'current')
            elif kind in self.END_EVENTS:
                if turn:
                    self.active.discard(turn)
                    self.active.discard('current')
                else:
                    self.active.clear()


class Reader:
    def __init__(self, codex=CODEX, cli_only=False, registration_loader=registrations, discover=False):
        self.codex = codex
        self.traces = {}
        self.cli_only = cli_only
        self.registration_loader = registration_loader
        self.discovery = None
        self.claude = None
        if discover:
            from terminal_discovery import TerminalDiscovery
            from claude_sessions import ClaudeSessions
            self.discovery = TerminalDiscovery()
            self.claude = ClaudeSessions()

    def close(self):
        if self.discovery:
            self.discovery.close()

    def snapshot(self, now=None):
        now = now or dt.datetime.now().astimezone()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        terminals = self.registration_loader() if self.cli_only else {}
        terminals = {ident: record for ident, record in terminals.items() if record.get('started_at', 0) >= midnight}
        db = self.codex / 'state_5.sqlite'
        if not db.exists() and self.claude is None:
            raise RuntimeError('No se encuentra la base local de chats de Codex.')
        rows = []
        if db.exists():
            with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2)) as connection:
                extra = ' OR id IN (' + ','.join('?' for _ in terminals) + ')' if terminals else ''
                columns = {row[1] for row in connection.execute('PRAGMA table_info(threads)')}
                title = "COALESCE(NULLIF(name,''),title)" if 'name' in columns else 'title'
                cwd = 'cwd' if 'cwd' in columns else "''"
                name = 'name' if 'name' in columns else "''"
                fields = f'id, {title}, rollout_path, source, {cwd}, {name}, title, updated_at'
                if self.discovery:
                    rows = connection.execute(f'''SELECT {fields} FROM threads WHERE archived=0
                        AND attached_thread_parent_id IS NULL ORDER BY updated_at DESC LIMIT 500''').fetchall()
                else:
                    rows = connection.execute(f'''SELECT {fields}
                        FROM threads WHERE archived=0 AND (updated_at>=?{extra})
                        AND attached_thread_parent_id IS NULL ORDER BY updated_at DESC''', (midnight, *terminals)).fetchall()
        if self.discovery:
            from terminal_discovery import native_clients
            clients = native_clients()
            metadata = [{'id': row[0], 'cwd': row[4], 'name': row[5], 'title': row[6], 'recent': row[7] >= midnight} for row in rows]
            metadata.extend(self.claude.metadata(clients, now))
            terminals.update(self.discovery.update(metadata, clients=clients))
        result = []
        seen = set()
        for ident, title, path, source, cwd, name, original_title, updated_at in rows:
            if 'subagent' in source.lower():
                continue
            if self.cli_only and source not in ('cli', '"cli"') and ident not in terminals:
                continue
            if updated_at < midnight and ident not in terminals:
                continue
            seen.add(ident)
            if ident not in self.traces or self.traces[ident].path != Path(path):
                self.traces[ident] = Trace(path)
            trace = self.traces[ident]
            try:
                trace.read()
            except FileNotFoundError:
                continue
            # Actual turn activity, rather than a rename or metadata update.
            terminal = terminals.get(ident)
            if not terminal and (trace.last_activity is None or trace.last_activity.date() != now.date()):
                continue
            state = 'working' if trace.active else 'sleeping'
            if terminal and not terminal.get('live'):
                state = 'sleeping'
            chat = {'id': ident, 'title': title or 'Chat de Codex', 'state': state}
            if self.cli_only:
                chat['provider'] = 'codex'
                chat['terminal'] = terminal
                chat['project'] = safe_preview(str(cwd).replace('\\', '/').rstrip('/').rsplit('/', 1)[-1], 60)
                chat['activity'] = trace.activity.summary()
            result.append(chat)
        self.traces = {key: trace for key, trace in self.traces.items() if key in seen}
        if self.claude:
            result.extend(self.claude.snapshot(terminals))
        return result


def serve():
    import tkinter as tk
    from session_details import DetailsCard, compact_caption
    from avatar_personality import ACCESSORIES, COLORS, COLOR_NAMES, Notices, customize, identity, render_frames, visual_state
    from PIL import Image, ImageTk
    import ctypes
    import msvcrt
    # Keep Tk window coordinates aligned with physical pixels on scaled displays.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    STATE.mkdir(parents=True, exist_ok=True)
    lock = (STATE / 'instance.lock').open('a+b')
    lock.seek(0)
    lock.write(b'1')
    lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        return
    root = tk.Tk()
    root.withdraw()
    root.title('Codex Float')
    identities = load_json(STATE / 'identities.json', {})
    notices = Notices(load_json(STATE / 'notices.json', {}))
    quiet = tk.BooleanVar(value=load_json(STATE / 'preferences.json', {}).get('quiet', False))

    def save_quiet():
        atomic_json(STATE / 'preferences.json', {'quiet': quiet.get()})

    def acknowledge(ident):
        if notices.acknowledge(ident):
            atomic_json(STATE / 'notices.json', notices.records)

    def animation(entry, state):
        if state not in entry['animations']:
            images = render_frames(state, entry['accent'], entry['accessory'], entry['theme']['background'])
            entry['animations'][state] = (
                [ImageTk.PhotoImage(frame) for frame in images],
                [ImageTk.PhotoImage(frame.resize((80, 52), Image.Resampling.LANCZOS)) for frame in images])
        return entry['animations'][state]
    positions_path = STATE / 'positions.json'
    positions = load_json(positions_path, {})
    widgets = {}
    themes = ThemeSettings(STATE / 'themes.json')

    def refresh_themes(force=False):
        if themes.reload(force):
            for entry in widgets.values():
                theme = themes.get(entry['chat'].get('provider'))
                entry['theme'] = theme
                for surface in ('window', 'title', 'picture', 'label', 'badge'):
                    entry[surface].configure(bg=theme['background'])
                entry['title'].configure(fg=theme['foreground'])
                entry['label'].configure(fg=theme['foreground'])
                entry['badge'].configure(fg=theme['notice'])
                entry['animations'].clear()
                entry['frame'] = 0
                visual = entry['visual'] or visual_state(entry['chat'])
                entry['picture'].configure(image=animation(entry, visual)[0 if entry['size'] == FULL_SIZE else 1][0])

    updates = queue.Queue(maxsize=1)
    stop = threading.Event()
    reader = Reader(cli_only=True, discover=True)
    last_error = None
    native = Windows()
    bindings_path = STATE / 'window-bindings.json'
    bindings = load_json(bindings_path, {})
    selected = None
    pending = None
    bind_request = None
    focus_error = None
    selection_epoch = 0
    layout_path = STATE / 'layout.json'
    layout = load_json(layout_path, {'mode': 'top', 'manual': [], 'order': []})
    if layout.get('mode') not in ('top', 'right', 'left'):
        layout['mode'] = 'top'
    manual_ids = set(layout.get('manual', []))
    layout_order = list(layout.get('order', []))
    layout_area = monitor_work_area()
    follow_selection = False
    avatars_hidden = False
    hotkeys = GlobalHotkeys()

    def toggle_visibility():
        nonlocal avatars_hidden
        avatars_hidden = not avatars_hidden
        details.hide()
        for entry in widgets.values():
            entry['drag'].clear()
            if avatars_hidden:
                entry['window'].withdraw()
            else:
                entry['window'].deiconify()

    def save_layout():
        layout.update(manual=sorted(manual_ids), order=layout_order)
        atomic_json(layout_path, layout)

    def apply_layout(anchor):
        nonlocal layout_area, follow_selection
        details.hide()
        layout['mode'] = anchor
        layout_area = monitor_work_area()
        follow_selection = False
        manual_ids.difference_update(widgets)
        for entry in widgets.values():
            entry['manual'] = False
            entry['docked'] = False
        save_layout()

    def position_group():
        items = [(ident, *widgets[ident]['size']) for ident in layout_order
            if ident in widgets and not widgets[ident]['manual'] and not widgets[ident]['docked']]
        for ident, (x, y) in arrange(items, layout_area, layout['mode']).items():
            window = widgets[ident]['window']
            if (window.winfo_x(), window.winfo_y()) != (x, y):
                window.geometry(f'{x:+d}{y:+d}')
            positions[ident] = [x, y]

    def bound_window(ident):
        binding = bindings.get(ident)
        if binding:
            terminal = widgets.get(ident, {}).get('terminal') or {}
            if not binding.get('manual') and terminal.get('kind') == 'unbound':
                return None
            window = native.inspect(binding['hwnd'])
            if window and window.pid == binding['pid'] and window.executable == binding['executable']:
                return window
        return None

    def associate(ident, window, manual=False):
        nonlocal selected, focus_error, selection_epoch, follow_selection
        bindings[ident] = {'hwnd': window.hwnd, 'pid': window.pid, 'executable': window.executable, 'manual': manual}
        atomic_json(bindings_path, bindings)
        selected = ident
        selection_epoch = time.time()
        focus_error = None
        widgets[ident]['docked'] = True
        widgets[ident]['greet_until'] = time.monotonic() + 1.2
        acknowledge(ident)
        follow_selection = True

    def open_chat(ident):
        nonlocal pending, selected, focus_error
        details.hide()
        entry = widgets[ident]
        entry['drag'].clear()
        target = bound_window(ident)
        terminal = entry.get('terminal') or {}
        if target and (bindings.get(ident, {}).get('manual') or terminal.get('live')):
            if not native.activate(target):
                focus_error = 'Windows no permitió activar la terminal. Selecciónala y vuelve a intentar.'
                return 'break'
            if terminal.get('kind') == 'tab':
                from terminal_discovery import select_tab
                try:
                    select_tab(terminal)
                except RuntimeError as error:
                    focus_error = str(error)
                    return 'break'
            associate(ident, target, manual=bindings.get(ident, {}).get('manual', False))
            return 'break'
        try:
            if entry['chat'].get('provider') == 'claude':
                from claude_sessions import launch_claude
                launch_claude(entry['chat'])
            else:
                launch(ident)
            pending = (ident, time.monotonic() + 20)
            focus_error = None
        except (OSError, RuntimeError, ValueError) as error:
            focus_error = str(error)
        return 'break'

    def bind_to_next_window(ident):
        nonlocal bind_request, focus_error
        bind_request = (ident, time.monotonic() + 8)
        focus_error = None

    details = DetailsCard(root, widgets, open_chat, on_view=acknowledge)

    def worker():
        try:
            while not stop.is_set():
                try:
                    update = (reader.snapshot(), None)
                except Exception as error:
                    update = (None, f'{type(error).__name__}: {error}')
                try:
                    updates.get_nowait()
                except queue.Empty:
                    pass
                updates.put(update)
                stop.wait(2)
        finally:
            reader.close()

    def bounds():
        user32 = ctypes.windll.user32
        return tuple(user32.GetSystemMetrics(index) for index in (76, 77, 78, 79))

    def clamp(x, y, size=FULL_SIZE):
        left, top, width, height = bounds()
        return max(left, min(x, left + width - size[0])), max(top, min(y, top + height - size[1]))

    def save_position(ident, window):
        if ident in widgets and widgets[ident]['docked']:
            return
        positions[ident] = [window.winfo_x(), window.winfo_y()]
        atomic_json(positions_path, positions)

    def quit_all():
        stop.set()
        hotkeys.close()
        for ident, entry in widgets.items():
            save_position(ident, entry['window'])
        atomic_json(STATE / 'status.json', {'heartbeat': 0, 'running': False})
        root.destroy()

    def make_widget(chat):
        ident = chat['id']
        known_identity = ident in identities
        accent, accessory = identity(ident, identities)
        theme = themes.get(chat.get('provider'))
        if not known_identity:
            atomic_json(STATE / 'identities.json', identities)
        window = tk.Toplevel(root)
        window.withdraw()
        window.title('Codex Float - ' + chat['title'])
        window.overrideredirect(True)
        window.attributes('-topmost', True)
        window.configure(bg=theme['background'], highlightbackground='#46536b', highlightthickness=1)
        window.attributes('-alpha', 1)
        width, height = HALF_SIZE
        location = positions.get(ident, [layout_area[0] + 12, layout_area[1] + 12])
        x, y = clamp(int(location[0]), int(location[1]), HALF_SIZE)
        positions.setdefault(ident, [x, y])
        window.geometry(f'{width}x{height}{x:+d}{y:+d}')
        title = tk.Label(window, text=chat['title'][:12], bg=theme['background'], fg=theme['foreground'], font=('Segoe UI', 6), anchor='center', pady=0, padx=0, borderwidth=0)
        title.pack(fill='x')
        picture = tk.Label(window, bg=theme['background'], borderwidth=0, padx=0, pady=0)
        picture.pack()
        label = tk.Label(window, bg=theme['background'], fg=theme['foreground'], font=('Segoe UI', 6), pady=0, padx=0, borderwidth=0)
        label.pack()
        drag = {}
        entry = {'window': window, 'picture': picture, 'title': title, 'label': label, 'state': chat['state'], 'frame': 0, 'size': HALF_SIZE, 'docked': False, 'drag': drag, 'chat_title': chat['title'], 'manual': ident in manual_ids}
        entry.update(accent=accent, accessory=accessory, theme=theme, animations={}, visual=None, celebrate_until=0, greet_until=0)
        badge = tk.Label(window, text='●', fg=theme['notice'], bg=theme['background'], font=('Segoe UI', 8), borderwidth=0, padx=0, pady=0)
        entry['badge'] = badge
        xp_bar = tk.Frame(window, bg=accent, height=2, borderwidth=0)
        entry['xp_bar'] = xp_bar
        entry['chat'] = chat
        widgets[ident] = entry
        if ident not in layout_order:
            layout_order.append(ident)
            save_layout()

        def press(event):
            details.hide()
            drag.update(x=event.x_root - window.winfo_x(), y=event.y_root - window.winfo_y())

        def move(event):
            if drag:
                entry['docked'] = False
                entry['manual'] = True
                manual_ids.add(ident)
                x, y = clamp(event.x_root - drag['x'], event.y_root - drag['y'], entry['size'])
                window.geometry(f'{x:+d}{y:+d}')

        def release(event):
            save_position(ident, window)
            if entry['manual']:
                save_layout()
            drag.clear()

        menu = tk.Menu(window, tearoff=False)
        menu.add_command(label='Ver detalles de la sesión', command=lambda: details.show(ident, pinned=True))
        menu.add_command(label='Perfil · nivel y estadísticas', command=lambda: details.show(ident, pinned=True, profile=True))
        menu.add_command(label='Abrir terminal y seleccionar', command=lambda: open_chat(ident))
        menu.add_command(label='Vincular: elige una ventana en 8 s', command=lambda: bind_to_next_window(ident))
        menu.add_separator()
        appearance_menu = tk.Menu(menu, tearoff=False)
        color_choice = tk.IntVar(value=COLORS.index(accent))
        accessory_choice = tk.IntVar(value=accessory)

        def change_appearance(reset=False):
            accent, accessory = customize(ident, identities, color_choice.get(), accessory_choice.get(), reset=reset)
            atomic_json(STATE / 'identities.json', identities)
            color_choice.set(COLORS.index(accent))
            accessory_choice.set(accessory)
            entry.update(accent=accent, accessory=accessory, frame=0)
            entry['xp_bar'].configure(bg=accent)
            entry['title'].configure(fg=entry['theme']['foreground'])
            entry['animations'].clear()
            visual = entry['visual'] or visual_state(entry['chat'])
            entry['picture'].configure(image=animation(entry, visual)[0 if entry['size'] == FULL_SIZE else 1][0])
            details.refresh()

        color_menu = tk.Menu(appearance_menu, tearoff=False)
        for index, name in enumerate(COLOR_NAMES):
            color_menu.add_radiobutton(label=name, variable=color_choice, value=index, command=change_appearance)
        appearance_menu.add_cascade(label='Color', menu=color_menu)
        accessory_menu = tk.Menu(appearance_menu, tearoff=False)
        for index, name in enumerate(ACCESSORIES):
            accessory_menu.add_radiobutton(label=name, variable=accessory_choice, value=index, command=change_appearance)
        appearance_menu.add_cascade(label='Accesorio', menu=accessory_menu)
        appearance_menu.add_separator()
        appearance_menu.add_command(label='Restablecer aspecto automático', command=lambda: change_appearance(reset=True))
        menu.add_cascade(label='Personalizar compañero', menu=appearance_menu)
        for anchor, placement_label in [('top', 'Arriba centro'), ('right', 'Derecha centro'), ('left', 'Izquierda centro')]:
            menu.add_command(label=placement_label, accelerator=hotkeys.labels.get(anchor, ''), command=lambda mode=anchor: apply_layout(mode))
        menu.add_separator()
        menu.add_checkbutton(label='Modo tranquilo', variable=quiet, command=save_quiet)
        menu.add_command(label='Editar colores globales', command=edit_themes)
        menu.add_command(label='Recargar colores', command=lambda: refresh_themes(force=True))
        if hotkeys.labels.get('toggle_visibility'):
            menu.add_command(label='Ocultar avatares', accelerator=hotkeys.labels['toggle_visibility'], command=toggle_visibility)
        menu.add_command(label='Apagar todos', command=quit_all)
        menu.add_command(label='Cerrar menu')

        def show_menu(event):
            return details.popup_menu(menu, event.x_root, event.y_root)

        for surface in (window, title, picture, label, badge, xp_bar):
            surface.bind('<ButtonPress-1>', press)
            surface.bind('<B1-Motion>', move)
            surface.bind('<ButtonRelease-1>', release)
            surface.bind('<Double-Button-1>', lambda event: open_chat(ident))
            surface.bind('<Button-3>', show_menu)
            surface.bind('<Enter>', lambda event: details.request(ident))
            surface.bind('<Leave>', lambda event: details.leave())

    tick_number = 0

    def tick():
        nonlocal last_error, tick_number, selected, pending, bind_request, focus_error
        if tick_number % 10 == 0:
            refresh_themes()
        if (STATE / 'stop').exists():
            (STATE / 'stop').unlink(missing_ok=True)
            quit_all()
            return
        while True:
            try:
                action = hotkeys.events.get_nowait()
                if action == 'toggle_visibility':
                    toggle_visibility()
                else:
                    apply_layout(action)
            except queue.Empty:
                break
        try:
            chats, error = updates.get_nowait()
            last_error = error
            if chats is not None:
                changed, celebrations = notices.observe(chats, time.time())
                if changed:
                    atomic_json(STATE / 'notices.json', notices.records)
                wanted = {chat['id'] for chat in chats}
                for ident in list(widgets):
                    if ident not in wanted:
                        save_position(ident, widgets[ident]['window'])
                        widgets.pop(ident)['window'].destroy()
                        if selected == ident:
                            selected = None
                for chat in chats:
                    if chat['id'] not in widgets:
                        make_widget(chat)
                    entry = widgets[chat['id']]
                    if chat['id'] in celebrations:
                        entry['celebrate_until'] = time.monotonic() + 3
                    if entry['state'] != chat['state']:
                        entry['frame'] = 0
                    entry['state'] = chat['state']
                    entry['chat'] = chat
                    entry['observed_at'] = time.time()
                    entry['chat_title'] = chat['title']
                    entry['terminal'] = chat.get('terminal')
                    terminal = chat.get('terminal') or {}
                    host = native.inspect(terminal.get('hwnd')) if terminal.get('live') else None
                    if host and host.pid == terminal.get('window_pid') and (terminal.get('kind') == 'tab' or terminal.get('token') in host.title):
                        binding = {'hwnd': host.hwnd, 'pid': host.pid, 'executable': host.executable, 'manual': False}
                        if bindings.get(chat['id']) != binding:
                            bindings[chat['id']] = binding
                            atomic_json(bindings_path, bindings)
                    entry['window'].title('Codex Float - ' + chat['title'])
        except queue.Empty:
            pass
        foreground = native.foreground()
        active_window = native.inspect(foreground)
        if bind_request:
            ident, deadline = bind_request
            if ident not in widgets or time.monotonic() > deadline:
                bind_request = None
                focus_error = 'Vinculacion cancelada'
            elif active_window and active_window.terminal and active_window.visible and not active_window.minimized:
                associate(ident, active_window, manual=True)
                bind_request = None
        if pending:
            ident, deadline = pending
            if ident not in widgets or time.monotonic() > deadline:
                pending = None
                focus_error = 'No se encontró la terminal de la sesión.'
            elif (widgets[ident].get('terminal') or {}).get('live') and bound_window(ident):
                target = bound_window(ident)
                if native.activate(target):
                    associate(ident, target)
                else:
                    focus_error = 'Windows no permitió activar la terminal. Selecciónala y vuelve a intentar.'
                pending = None
        valid_bindings = {}
        for ident, entry in widgets.items():
            host = bound_window(ident)
            if not host or not host.visible or host.minimized:
                continue
            terminal = entry.get('terminal') or {}
            if terminal.get('kind') == 'tab':
                # Do not highlight a CLI from an inactive tab of this window.
                fresh = terminal.get('heartbeat', 0) >= selection_epoch
                if (fresh and terminal.get('selected')) or (not fresh and ident == selected):
                    valid_bindings[ident] = host.hwnd
            elif terminal.get('live') or bindings.get(ident, {}).get('manual'):
                valid_bindings[ident] = host.hwnd
        next_selected = foreground_selection(valid_bindings, foreground, selected)
        if next_selected != selected:
            selected = next_selected
            if selected in widgets and follow_selection:
                widgets[selected]['docked'] = True
        for ident, entry in widgets.items():
            entry['unavailable'] = bool(last_error)
            desired = avatar_size(ident, selected)
            full = desired == FULL_SIZE
            active = ident == selected
            if not active:
                entry['docked'] = False
            if entry['size'] != desired:
                entry['size'] = desired
                entry['window'].geometry(f'{desired[0]}x{desired[1]}')
                entry['title'].configure(font=('Segoe UI', 9 if full else 6))
                entry['title'].pack_configure(pady=(5, 0) if full else 0)
                entry['label'].configure(font=('Segoe UI', 8 if full else 6))
                if not full:
                    entry['docked'] = False
                    x, y = clamp(*positions[ident], desired)
                    entry['window'].geometry(f'{x:+d}{y:+d}')
                elif not active:
                    x, y = clamp(entry['window'].winfo_x(), entry['window'].winfo_y(), desired)
                    entry['window'].geometry(f'{x:+d}{y:+d}')
            unread = notices.pending(ident)
            stats = (entry['chat'].get('activity') or {}).get('stats') or {}
            level = stats.get('level', 1)
            display_title = f'N{level} · ' + (entry['theme']['name'] + ' · ' if full else '') + entry['chat_title']
            entry['title'].configure(text=display_title[:(22 if full else 10) if unread else (25 if full else 12)])
            progress = stats.get('progress', 0) / stats.get('needed', 100)
            xp_signature = (progress, desired)
            if xp_signature != entry.get('xp_signature'):
                entry['xp_signature'] = xp_signature
                if progress:
                    entry['xp_bar'].place(x=2, rely=1, y=-4, width=max(1, round((desired[0] - 4) * progress)), height=2)
                    entry['xp_bar'].lift()
                else:
                    entry['xp_bar'].place_forget()
            if unread:
                entry['badge'].configure(font=('Segoe UI', 9 if full else 7))
                entry['badge'].place(relx=1, x=-3, y=3 if full else 0, anchor='ne')
                entry['badge'].lift()
            else:
                entry['badge'].place_forget()
            host = bound_window(ident)
            entry['minimized'] = bool(host and host.minimized)
            entry['window'].configure(highlightbackground='#858585' if entry['minimized'] else '#77e4c8' if active else '#46536b')
            if active and entry['docked']:
                location = dock_position(host.client, desired, host.dpi) if host and host.visible and not host.minimized else None
                if location:
                    entry['window'].geometry(f'{location[0]:+d}{location[1]:+d}')
                elif host:
                    # Minimized client coordinates are off-screen. Keep the last
                    # visible position while retaining docking for restoration.
                    x, y = clamp(entry['window'].winfo_x(), entry['window'].winfo_y(), desired)
                    entry['window'].geometry(f'{x:+d}{y:+d}')
                else:
                    # Keep a closed terminal's avatar clickable for resume.
                    entry['docked'] = False
                    x, y = clamp(*positions[ident], desired)
                    entry['window'].geometry(f'{x:+d}{y:+d}')
            if avatars_hidden:
                entry['window'].withdraw()
            elif entry['window'].state() == 'withdrawn':
                entry['window'].deiconify()
            state = entry['state']
            now = time.monotonic()
            celebrating = now < entry['celebrate_until'] and not quiet.get() and not last_error
            visual = visual_state(entry['chat'], celebrating=celebrating,
                greeting=now < entry['greet_until'] and not quiet.get(), carried=bool(entry['drag']) and not quiet.get())
            if visual != entry['visual'] or quiet.get() or last_error:
                entry['frame'] = 0
            elif state == 'working' or tick_number % 2 == 0:
                entry['frame'] = (entry['frame'] + 1) % 8
            entry['visual'] = visual
            entry['picture'].configure(image=animation(entry, visual)[0 if full else 1][entry['frame']])
            caption = compact_caption(entry['chat'], full)
            if state != 'working' and unread:
                caption = '¡Turno listo!' if celebrating else 'Resultado nuevo' if full else 'Nuevo'
            if pending and pending[0] == ident:
                caption = 'Abriendo...'
            if bind_request and bind_request[0] == ident:
                caption = 'Elige ventana'
            if entry.get('terminal') and not entry['terminal'].get('live'):
                caption = 'Reabrir CLI' if full else 'CLI cerrado'
            entry['label'].configure(text='Sin conexion' if last_error else caption,
                fg=entry['theme']['notice'] if last_error or unread else entry['theme']['foreground'])
        position_group()
        if not avatars_hidden and tick_number % 2 == 0:
            details.reconcile_pointer()
        if tick_number % 10 == 0:
            details.refresh()
        if tick_number % 10 == 0:
            atomic_json(STATE / 'status.json', {
                'running': True, 'heartbeat': time.time(), 'pid': os.getpid(),
                'chats': len(widgets),
                'working': sum(v['state'] == 'working' for v in widgets.values()),
                'error': last_error, 'focus_error': focus_error, 'selected': selected,
                'layout': layout['mode'], 'layout_area': list(layout_area),
                'hotkeys': hotkeys.labels, 'hotkey_error': hotkeys.error,
                'sizes': {ident: list(v['size']) for ident, v in widgets.items()},
                'docked': {ident: v['docked'] for ident, v in widgets.items()},
                'visible': {ident: v['window'].state() != 'withdrawn' for ident, v in widgets.items()},
                'minimized': {ident: v.get('minimized', False) for ident, v in widgets.items()},
                'windows': {ident: [v['window'].winfo_x(), v['window'].winfo_y()] for ident, v in widgets.items()},
                'details': {'session': details.ident, 'pinned': details.pinned, 'profile': details.profile},
                'quiet': quiet.get(),
                'hidden': avatars_hidden,
                'themes': themes.themes, 'theme_error': themes.error,
                'statistics': {ident: (v['chat'].get('activity') or {}).get('stats') for ident, v in widgets.items()},
                'theme_file': str(themes.path),
                'companions': {ident: {'accent': v['accent'], 'accessory': v['accessory'],
                    'provider': v['chat'].get('provider', 'codex'), 'background': v['theme']['background'],
                    'visual': v['visual'], 'pending_result': notices.pending(ident)} for ident, v in widgets.items()},
                'activity': {ident: {key: (v.get('chat', {}).get('activity') or {}).get(key)
                    for key in ('phase', 'started_at', 'finished_at', 'updated_at', 'action_count')} for ident, v in widgets.items()},
            })
        tick_number += 1
        root.after(100, tick)

    threading.Thread(target=worker, daemon=True).start()
    root.after(100, tick)
    try:
        root.mainloop()
    finally:
        stop.set()
        hotkeys.close()
        lock.close()


def edit_themes():
    path = STATE / 'themes.json'
    if not path.exists():
        write_config(path, DEFAULTS)
    subprocess.Popen(['notepad.exe', str(path)])


def theme_command(args, parser):
    path = STATE / 'themes.json'
    target = args.target or 'show'
    if target not in ('codex', 'claude', 'show', 'edit', 'reset'):
        parser.error('Usa theme codex|claude|show|edit|reset.')
    if target not in DEFAULTS and any((args.background, args.foreground, args.notice)):
        parser.error('Los colores requieren theme codex o theme claude.')
    if target == 'edit':
        edit_themes()
        return
    config = {} if target == 'reset' else read_config(path)
    if target in DEFAULTS:
        options = config.setdefault(target, {})
        for field in ('background', 'foreground', 'notice'):
            value = getattr(args, field)
            if value == 'auto' and field != 'background':
                options.pop(field, None)
            elif value is not None:
                options[field] = value
        write_config(path, config)
    elif target == 'reset':
        write_config(path, DEFAULTS)
        config = DEFAULTS
    print(str(path))
    print(json.dumps(palettes(config), indent=2))
    print('Los cambios se aplican automaticamente en aproximadamente 1 segundo si los avatares estan encendidos.')


def main():
    parser = argparse.ArgumentParser(description='Terminales Codex CLI y avatares flotantes de hoy.')
    parser.add_argument('command', nargs='?', default='toggle', choices=['on', 'off', 'toggle', 'status', 'serve', 'new', 'resume', 'list', 'theme', 'refresh'])
    parser.add_argument('target', nargs='?', help='Carpeta para new; UUID de sesion para resume.')
    parser.add_argument('--all', action='store_true', help='Incluye chats de la app en list para migrarlos al CLI.')
    parser.add_argument('--background', help='Fondo del proveedor en #RRGGBB (theme).')
    parser.add_argument('--foreground', help='Texto en #RRGGBB o auto (theme).')
    parser.add_argument('--notice', help='Avisos en #RRGGBB o auto (theme).')
    args = parser.parse_args()
    if args.command in ('theme', 'refresh'):
        try:
            if args.command == 'theme':
                theme_command(args, parser)
            else:
                config = read_config(STATE / 'themes.json')
                write_config(STATE / 'themes.json', config)
                if not running():
                    print('Colores validados. Se aplicaran al ejecutar codex-float on.')
                    return
                for _ in range(50):
                    status = running() or {}
                    if status.get('themes') == palettes(config) and not status.get('theme_error'):
                        print('Colores recargados sin reiniciar los avatares.')
                        return
                    time.sleep(.1)
                raise ValueError('No se pudo confirmar la recarga. Consulta codex-float status.')
        except (OSError, ValueError) as error:
            raise SystemExit(str(error))
        return
    if args.command == 'serve':
        serve()
        return
    if args.command in ('new', 'resume'):
        try:
            ident = create_session(args.target or os.getcwd()) if args.command == 'new' else args.target
            if not ident:
                parser.error('resume requiere el UUID de la sesion. Consulta codex-float list --all.')
            launch(ident)
            print(f'Codex CLI: {ident}')
        except (OSError, RuntimeError, ValueError) as error:
            raise SystemExit(str(error))
        if not running():
            subprocess.run([sys.executable, str(BASE / 'codex_float.py'), 'on'], check=True)
        return
    if args.command == 'list':
        reader = Reader(cli_only=not args.all, discover=not args.all)
        try:
            for chat in reader.snapshot():
                print(f'{chat["id"]}  {chat["state"]:8}  {chat["title"]}')
        finally:
            reader.close()
        return
    current = running()
    command = ('off' if current else 'on') if args.command == 'toggle' else args.command
    if command == 'status':
        print(json.dumps(current or {'running': False}, ensure_ascii=False, indent=2))
    elif command == 'off':
        if current:
            (STATE / 'stop').touch()
            for _ in range(40):
                if not running():
                    break
                time.sleep(.1)
            if running():
                raise SystemExit('No se pudo confirmar el apagado. Ejecuta codex-float status.')
        print('Codex Float apagado.')
    elif current:
        print('Codex Float ya esta encendido.')
    else:
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / 'stop').unlink(missing_ok=True)
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        with (STATE / 'app.log').open('a', encoding='utf-8') as log:
            subprocess.Popen([str(pythonw), str(BASE / 'codex_float.py'), 'serve'], cwd=BASE, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(60):
            if running():
                print('Codex Float encendido. Arrastra los terminales; clic derecho para apagar.')
                return
            time.sleep(.1)
        raise SystemExit(f'No se pudo iniciar. Revisa {STATE / "app.log"}')


if __name__ == '__main__':
    main()
