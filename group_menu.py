"""Small always-available group control and an on-demand history picker."""
import queue
import threading
import os

from session_activity import safe_preview
from session_history import history_label

MENU_SIZE = 36
MENU_ID = '__group_menu__'


class HistoryPicker:
    def __init__(self, root, loader, on_select, current_ids):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.loader, self.on_select, self.current_ids = root, loader, on_select, current_ids
        self.records = {}
        self.results = queue.Queue(maxsize=1)
        self.loading = False
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
        entry = ttk.Entry(search, textvariable=self.query)
        entry.pack(side='left', fill='x', expand=True)
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
        self.tree.bind('<Double-1>', lambda _: self.choose())
        self.message = tk.StringVar(value='Buscar por título, fecha o proveedor.')
        ttk.Label(self.window, textvariable=self.message, wraplength=480).pack(fill='x', padx=10, pady=6)
        footer = ttk.Frame(self.window)
        footer.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(footer, text='Actualizar', command=self.reload).pack(side='left')
        ttk.Button(footer, text='Mostrar avatar', command=self.choose).pack(side='right')

    def show(self):
        self.window.deiconify()
        self.window.lift()
        self.reload()

    def reload(self):
        if self.loading:
            return
        self.loading = True
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
        self.records = {record['id']: record for record in records}
        self.render()
        if warnings:
            self.message.set(' '.join(warnings))

    def render(self):
        self.tree.delete(*self.tree.get_children())
        query = self.query.get().casefold()
        current = self.current_ids()
        for ident, record in self.records.items():
            labels = history_label(record)
            if ident not in current and query in ' '.join(labels).casefold():
                self.tree.insert('', 'end', iid=ident, values=labels)
        if not self.loading:
            self.message.set(f'{len(self.tree.get_children())} sesiones · Mostrar un avatar no abre su terminal.')

    def choose(self):
        selected = self.tree.selection()
        if selected and selected[0] in self.records:
            self.on_select(self.records[selected[0]])
            self.window.withdraw()


class GroupMenu:
    def __init__(self, root, details, entries, hidden, individual_hidden, toggle_all, toggle_one, show_history, today_only,
                 sounds=None, quiet=lambda: False):
        import tkinter as tk
        from session_details import DetailsCard
        self.details, self.entries = details, entries
        self.hidden, self.individual_hidden = hidden, individual_hidden
        self.toggle_all, self.toggle_one = toggle_all, toggle_one
        self.show_history, self.today_only = show_history, today_only
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
        self.canvas.create_oval(1, 1, 34, 34, fill='#263447', outline='#869bb2')
        for y in (10, 17, 24):
            self.canvas.create_oval(16, y, 19, y + 3, fill='#e0e8f3', outline='')
        self.menu = tk.Menu(self.window, tearoff=False)
        self.avatar_menu = tk.Menu(self.menu, tearoff=False)
        from agent_sounds import SoundMenu
        self.sound_menu = SoundMenu(self.menu, sounds, quiet) if sounds else None
        self.variables = []
        self.canvas.bind('<Button-1>', self.popup)
        self.canvas.bind('<Button-3>', self.popup)
        self.window.update_idletasks()
        DetailsCard.no_activate(self)

    def place(self, x, y):
        if (self.window.winfo_x(), self.window.winfo_y()) != (x, y):
            self.window.geometry(f'{MENU_SIZE}x{MENU_SIZE}{x:+d}{y:+d}')
        if self.window.state() == 'withdrawn':
            self.window.deiconify()

    def popup(self, event):
        import tkinter as tk
        self.menu.delete(0, 'end')
        self.avatar_menu.delete(0, 'end')
        self.variables.clear()
        self.menu.add_command(label='Mostrar avatares' if self.hidden() else 'Ocultar avatares', command=self.toggle_all)
        for ident, entry in self.entries.items():
            variable = tk.BooleanVar(value=ident not in self.individual_hidden())
            self.variables.append(variable)
            provider = 'Claude' if entry['chat'].get('provider') == 'claude' else 'Codex'
            label = provider + ' · ' + safe_preview(entry['chat_title'], 55)
            self.avatar_menu.add_checkbutton(label=label, variable=variable, command=lambda key=ident: self.toggle_one(key))
        self.menu.add_cascade(label='Avatares visibles', menu=self.avatar_menu, state='normal' if self.entries else 'disabled')
        self.menu.add_separator()
        self.menu.add_command(label='Sesiones anteriores…', command=self.show_history)
        self.menu.add_command(label='Volver a sesiones de hoy', command=self.today_only)
        if self.sound_menu:
            self.menu.add_separator()
            self.sound_menu.refresh()
            self.menu.add_cascade(label='Sonidos', menu=self.sound_menu.menu)
        return self.details.popup_menu(self.menu, event.x_root, event.y_root)
