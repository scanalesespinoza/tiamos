"""On-demand attention list; all events and persistence belong to the model."""
import tkinter as tk
from tkinter import ttk


class AttentionWindow:
    def __init__(self, root, rows, open_session, acknowledge, before_show=lambda: None):
        self.root, self.get_rows = root, rows
        self.open_session, self.acknowledge, self.before_show = open_session, acknowledge, before_show
        self.window = None
        self.rows = {}
        self.signature = None

    def visible(self):
        return self.window is not None and self.window.state() != 'withdrawn'

    def show(self):
        self.before_show()
        if self.window is None:
            self._build()
        self.window.deiconify()
        self.window.lift()
        self.refresh()
        self.tree.focus_set()

    def _build(self):
        self.window = tk.Toplevel(self.root)
        self.window.withdraw()
        self.window.title('Necesita tu atención · tiamos')
        self.window.geometry('680x330')
        self.window.minsize(520, 250)
        self.window.attributes('-topmost', True)
        self.window.protocol('WM_DELETE_WINDOW', self.window.withdraw)
        ttk.Label(self.window, text='Necesita tu atención', font=('Segoe UI', 12, 'bold')).pack(anchor='w', padx=14, pady=(12, 4))
        ttk.Label(self.window, text='Revisa los avisos; las solicitudes se responden en su terminal.').pack(anchor='w', padx=14, pady=(0, 10))
        body = ttk.Frame(self.window)
        body.pack(fill='both', expand=True, padx=14)
        self.tree = ttk.Treeview(body, columns=('session', 'reason', 'age'), show='headings', selectmode='browse')
        for key, label, width in [('session', 'Sesión', 220), ('reason', 'Motivo', 280), ('age', 'Hace', 75)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=50)
        scroll = ttk.Scrollbar(body, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda _: self._selection())
        self.tree.bind('<Return>', lambda _: self.open_selected())
        self.tree.bind('<Control-Return>', lambda _: self.mark_seen())
        self.tree.bind('<Double-1>', self._double_click)
        self.window.bind('<Escape>', lambda _: self.window.withdraw())
        self.window.bind('<Control-Return>', lambda _: self.mark_seen())
        self.message = tk.StringVar()
        ttk.Label(self.window, textvariable=self.message, wraplength=640).pack(fill='x', padx=14, pady=8)
        footer = ttk.Frame(self.window)
        footer.pack(fill='x', padx=14, pady=(0, 12))
        self.seen_button = ttk.Button(footer, text='Marcar visto', command=self.mark_seen)
        self.seen_button.pack(side='left')
        self.open_button = ttk.Button(footer, text='Ir a la sesión', command=self.open_selected)
        self.open_button.pack(side='right')

    def refresh(self):
        if not self.visible():
            return
        rows = self.get_rows()
        signature = tuple(tuple(row.items()) for row in rows)
        if signature == self.signature:
            return
        self.signature = signature
        selected = self.tree.selection()
        self.rows = {row['key']: row for row in rows}
        for key in self.tree.get_children():
            if key not in self.rows:
                self.tree.delete(key)
        for index, row in enumerate(rows):
            values = (row['session'], row['reason'], row['age'])
            if self.tree.exists(row['key']):
                if tuple(self.tree.item(row['key'], 'values')) != values:
                    self.tree.item(row['key'], values=values)
            else:
                self.tree.insert('', index, iid=row['key'], values=values)
            self.tree.move(row['key'], '', index)
        target = selected[0] if selected and selected[0] in self.rows else next(iter(self.rows), None)
        if target:
            self.tree.selection_set(target)
            self.tree.focus(target)
        self._selection()

    def selected(self):
        selection = self.tree.selection()
        return self.rows.get(selection[0]) if selection else None

    def _selection(self):
        row = self.selected()
        self.open_button.configure(state='normal' if row and row['available'] else 'disabled')
        self.seen_button.configure(state='normal' if row and row['kind'] != 'input' else 'disabled')
        if not self.rows:
            message = 'No hay avisos pendientes.'
        elif row and row['kind'] == 'input':
            message = 'Esta solicitud sigue pendiente. Responde en la terminal; verla no la resuelve.'
        elif row and row['stale']:
            message = 'Aviso conservado; la sesión no está disponible. Puedes marcarlo como visto.'
        else:
            message = 'Enter: ir a la sesión · Ctrl+Enter: marcar visto · Esc: cerrar'
        self.message.set(message)

    def _double_click(self, event):
        key = self.tree.identify_row(event.y)
        if key:
            self.tree.selection_set(key)
            self.open_selected()
        return 'break'

    def open_selected(self):
        row = self.selected()
        # Session discovery may have changed since the last visible refresh.
        current = next((item for item in self.get_rows() if row and item['key'] == row['key']), None)
        if current and current['available']:
            self.open_session(row['id'])
        else:
            self.refresh()
        return 'break'

    def mark_seen(self):
        row = self.selected()
        if row and row['kind'] != 'input':
            self.acknowledge(row)
            self.refresh()
        return 'break'
