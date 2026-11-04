"""Small always-available group control and an on-demand history picker."""
import queue
import threading
import os

from session_activity import safe_preview
from session_history import history_label

MENU_SIZE = 36
MENU_ID = '__group_menu__'


def team_status(entries, hidden=False, excluded=()):
    """Describe observed state, including hidden sessions, without guessing intent."""
    counts = dict(total=len(entries), working=0, resting=0, unknown=0, attention=0, visible=0)
    for ident, entry in entries.items():
        chat = entry.get('chat') or {}
        state = entry.get('state', chat.get('state'))
        activity = chat.get('activity') or {}
        if entry.get('unavailable') or state not in ('working', 'sleeping'):
            counts['unknown'] += 1
        elif state == 'working':
            counts['working'] += 1
            latest = (activity.get('actions') or [{}])[0]
            if activity.get('phase') == 'Esperando intervención' or latest.get('outcome') == 'error':
                counts['attention'] += 1
        else:
            counts['resting'] += 1
        counts['visible'] += int(not hidden and ident not in excluded)
    return counts


class HistoryPicker:
    def __init__(self, root, loader, on_select, current_ids):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.loader, self.on_select, self.current_ids = root, loader, on_select, current_ids
        self.records = {}
        self.results = queue.Queue(maxsize=1)
        self.loading = False
        self.warnings = []
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title('Sesiones anteriores · Agentlings')
        self.window.geometry('520x340')
        self.window.minsize(400, 260)
        self.window.attributes('-topmost', True)
        self.window.protocol('WM_DELETE_WINDOW', self.window.withdraw)
        self.query = tk.StringVar()
        search = ttk.Frame(self.window)
        search.pack(fill='x', padx=10, pady=10)
        ttk.Label(search, text='Buscar:').pack(side='left', padx=(0, 6))
        self.search = ttk.Entry(search, textvariable=self.query)
        self.search.pack(side='left', fill='x', expand=True)
        self.search.bind('<Down>', self.focus_results)
        self.query.trace_add('write', lambda *_: self.render())
        body = ttk.Frame(self.window)
        body.pack(fill='both', expand=True, padx=10)
        self.tree = ttk.Treeview(body, columns=('date', 'provider', 'title'), show='headings', selectmode='browse')
        for key, label, width in [('date', 'Última actividad', 110), ('provider', 'CLI', 60), ('title', 'Sesión', 300)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=40)
        scroll = ttk.Scrollbar(body, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-1>', self.double_click)
        self.tree.bind('<Return>', lambda _: self.choose())
        self.tree.bind('<<TreeviewSelect>>', lambda _: self.sync_buttons())
        self.window.bind('<Escape>', lambda _: self.window.withdraw())
        self.message = tk.StringVar(value='Buscar por título, fecha o proveedor.')
        ttk.Label(self.window, textvariable=self.message, wraplength=480).pack(fill='x', padx=10, pady=6)
        footer = ttk.Frame(self.window)
        footer.pack(fill='x', padx=10, pady=(0, 10))
        self.reload_button = ttk.Button(footer, text='Actualizar', command=self.reload)
        self.reload_button.pack(side='left')
        self.choose_button = ttk.Button(footer, text='Mostrar avatar', command=self.choose, state='disabled')
        self.choose_button.pack(side='right')

    def show(self):
        self.window.deiconify()
        self.window.lift()
        self.search.focus_force()
        self.reload()

    def reload(self):
        if self.loading:
            return
        self.loading = True
        self.sync_buttons()
        self.message.set('Consultando historial local…')
        def load():
            try:
                self.results.put(self.loader())
            except Exception:
                self.results.put(([], ['No se pudo consultar el historial local.']))
        threading.Thread(target=load, daemon=True).start()

    def poll(self):
        try:
            records, warnings = self.results.get_nowait()
        except queue.Empty:
            return
        self.loading = False
        self.warnings = warnings
        self.records = {record['id']: record for record in records}
        self.render()

    def render(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        query = self.query.get().strip().casefold()
        current = self.current_ids()
        for ident, record in self.records.items():
            labels = history_label(record)
            if ident not in current and query in ' '.join(labels).casefold():
                self.tree.insert('', 'end', iid=ident, values=labels)
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
            self.tree.see(selected[0])
        if not self.loading:
            count = len(self.tree.get_children())
            if count:
                label = '1 sesión' if count == 1 else f'{count} sesiones'
                message = f'{label} · Mostrar un avatar no abre su terminal.'
            elif query and any(ident not in current for ident in self.records):
                message = 'Sin coincidencias. Prueba otro texto o borra la búsqueda.'
            else:
                message = 'No hay sesiones anteriores para mostrar.'
            self.message.set(' '.join([message, *self.warnings]))
        self.sync_buttons()

    def sync_buttons(self):
        selected = self.tree.selection()
        eligible = bool(selected and selected[0] in self.records and selected[0] not in self.current_ids())
        self.choose_button.configure(state='normal' if eligible and not self.loading else 'disabled')
        self.reload_button.configure(state='disabled' if self.loading else 'normal')

    def focus_results(self, event=None):
        rows = self.tree.get_children()
        if rows:
            if not self.tree.selection():
                self.tree.selection_set(rows[0])
            self.tree.focus(self.tree.selection()[0])
            self.tree.focus_set()
        return 'break'

    def double_click(self, event):
        ident = self.tree.identify_row(event.y)
        if ident:
            self.tree.selection_set(ident)
            self.choose()
        return 'break'

    def choose(self):
        selected = self.tree.selection()
        if self.loading or not selected or selected[0] not in self.records:
            return 'break'
        if selected[0] in self.current_ids():
            self.render()
            return 'break'
        try:
            self.on_select(self.records[selected[0]])
        except (OSError, ValueError, RuntimeError):
            self.message.set('No se pudo mostrar el avatar. Vuelve a intentarlo.')
        else:
            self.window.withdraw()
        return 'break'


class GroupMenu:
    def __init__(self, root, details, entries, hidden, individual_hidden, toggle_all, toggle_one, show_history, today_only,
                 sounds=None, quiet=lambda: False, *, show_all=None, set_quiet=None, place_group=None,
                 shutdown=None, hotkeys=None):
        import tkinter as tk
        from session_details import DetailsCard
        self.details, self.entries = details, entries
        self.hidden, self.individual_hidden = hidden, individual_hidden
        self.toggle_all, self.toggle_one = toggle_all, toggle_one
        self.show_history, self.today_only = show_history, today_only
        self.show_all, self.set_quiet, self.quiet = show_all, set_quiet, quiet
        self.place_group, self.shutdown, self.hotkeys = place_group, shutdown, hotkeys or {}
        self.quiet_choice = tk.BooleanVar(master=root)
        self.summary, self.indicator_color = {}, None
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title('Agentlings · Menú')
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        transparent = '#ff00ff' if os.name == 'nt' else '#263447'
        self.window.configure(bg=transparent)
        if os.name == 'nt':
            self.window.attributes('-transparentcolor', transparent)
        self.window.geometry(f'{MENU_SIZE}x{MENU_SIZE}+0+0')
        self.canvas = tk.Canvas(self.window, width=MENU_SIZE, height=MENU_SIZE, bg=transparent,
                                highlightthickness=0, cursor='hand2')
        self.canvas.pack()
        self.outline = self.canvas.create_oval(2, 2, 33, 33, fill='#263447', outline='#869bb2', width=2)
        for y in (10, 17, 24):
            self.canvas.create_oval(16, y, 19, y + 3, fill='#e0e8f3', outline='')
        self.menu = tk.Menu(self.window, tearoff=False)
        self.avatar_menu = tk.Menu(self.menu, tearoff=False)
        self.placement_menu = tk.Menu(self.menu, tearoff=False)
        from agent_sounds import SoundMenu
        self.sound_menu = SoundMenu(self.menu, sounds, quiet) if sounds else None
        self.variables = []
        self.canvas.bind('<Button-1>', self.popup)
        self.canvas.bind('<Button-3>', self.popup)
        self.window.update_idletasks()
        DetailsCard.no_activate(self)

    def refresh_indicator(self):
        self.summary = team_status(self.entries, self.hidden(), self.individual_hidden())
        color = '#f0bd75' if self.summary['attention'] else '#77e4c8' if self.summary['working'] else '#869bb2'
        if color != self.indicator_color:
            self.canvas.itemconfigure(self.outline, outline=color)
            self.indicator_color = color

    def place(self, x, y):
        if (self.window.winfo_x(), self.window.winfo_y()) != (x, y):
            self.window.geometry(f'{MENU_SIZE}x{MENU_SIZE}{x:+d}{y:+d}')
        if self.window.state() == 'withdrawn':
            self.window.deiconify()

    def popup(self, event):
        import tkinter as tk
        self.menu.delete(0, 'end')
        self.avatar_menu.delete(0, 'end')
        self.placement_menu.delete(0, 'end')
        self.variables.clear()
        self.refresh_indicator()
        summary = self.summary
        self.menu.add_command(label='Agentlings · ' + (f'{summary["total"]} sesión' if summary['total'] == 1 else f'{summary["total"]} sesiones'), state='disabled')
        parts = [f'{summary[key]} {label}' for key, label in [('working', 'trabajando'), ('resting', 'en descanso'), ('unknown', 'sin estado')]
                 if summary[key]]
        self.menu.add_command(label=' · '.join(parts) or 'Abre Codex o Claude CLI para empezar', state='disabled')
        visible = f'{summary["visible"]} de {summary["total"]} visibles'
        self.menu.add_command(label=(f'{summary["attention"]} por revisar · ' if summary['attention'] else '') + visible, state='disabled')
        self.menu.add_separator()
        self.menu.add_command(label='Mostrar avatares' if self.hidden() else 'Ocultar avatares', command=self.toggle_all,
                              accelerator=self.hotkeys.get('toggle_visibility', ''), state='normal' if self.entries else 'disabled')
        if self.show_all:
            self.menu.add_command(label='Mostrar todos los avatares', command=self.show_all,
                                  state='normal' if summary['visible'] < summary['total'] else 'disabled')
        for ident, entry in self.entries.items():
            variable = tk.BooleanVar(value=ident not in self.individual_hidden())
            self.variables.append(variable)
            provider = 'Claude' if entry['chat'].get('provider') == 'claude' else 'Codex'
            label = provider + ' · ' + safe_preview(entry['chat_title'], 55)
            self.avatar_menu.add_checkbutton(label=label, variable=variable, command=lambda key=ident: self.toggle_one(key))
        self.menu.add_cascade(label='Avatares visibles', menu=self.avatar_menu, state='normal' if self.entries else 'disabled')
        if self.place_group:
            for anchor, label in [('top', 'Arriba centro'), ('right', 'Derecha centro'), ('left', 'Izquierda centro')]:
                self.placement_menu.add_command(label=label, accelerator=self.hotkeys.get(anchor, ''),
                                               command=lambda mode=anchor: self.place_group(mode))
            self.menu.add_cascade(label='Ubicación', menu=self.placement_menu)
        if self.set_quiet:
            self.quiet_choice.set(self.quiet())
            self.menu.add_checkbutton(label='Modo tranquilo', variable=self.quiet_choice,
                                      command=lambda: self.set_quiet(self.quiet_choice.get()))
        self.menu.add_separator()
        self.menu.add_command(label='Sesiones anteriores…', command=self.show_history)
        self.menu.add_command(label='Volver a sesiones de hoy', command=self.today_only)
        if self.sound_menu:
            self.menu.add_separator()
            self.sound_menu.refresh()
            self.menu.add_cascade(label='Sonidos', menu=self.sound_menu.menu)
        if self.shutdown:
            self.menu.add_separator()
            self.menu.add_command(label='Apagar Agentlings', command=self.shutdown)
        return self.details.popup_menu(self.menu, event.x_root, event.y_root)
