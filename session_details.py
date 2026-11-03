"""A single, non-activating hover card for local session understanding."""
import time
from session_activity import safe_preview, time_text


def card_position(anchor, size, area, gap=10):
    left, top, right, bottom = area
    x, y, width, height = anchor
    card_width, card_height = size
    below = y + height + gap
    cy = below if below + card_height <= bottom else y - card_height - gap
    return (max(left, min(x + width // 2 - card_width // 2, right - card_width)),
        max(top, min(cy, bottom - card_height)))


def details_text(chat, now=None):
    now = time.time() if now is None else now
    activity = chat.get('activity') or {}
    terminal = chat.get('terminal') or {}
    working = chat.get('state') == 'working'
    state = 'Trabajando' if working else 'En descanso'
    if terminal and not terminal.get('live'):
        state = 'CLI cerrado · doble clic para reanudar'
    elif chat.get('minimized'):
        state += ' · terminal minimizada'
    started = activity.get('started_at')
    finished = activity.get('finished_at')
    if not working and finished and terminal.get('live'):
        state += ' · turno interrumpido' if activity.get('phase') == 'Turno interrumpido' else ' · turno terminado'
    duration = ''
    if started:
        end = now if working else finished
        if end:
            duration = ('Turno en curso · ' if working else 'Duración del último turno · ') + time_text(end - started)
    updated = activity.get('updated_at')
    observed = 'Sin actividad reciente disponible'
    if updated:
        observed = f"Última señal · hace {time_text(now - updated)}"
    phase = activity.get('phase') or 'En espera'
    if not working and not finished:
        phase = 'Sin turno en curso'
    lines = [phase, observed]
    if duration:
        lines.append(duration)
    count = activity.get('action_count', 0)
    if count:
        lines.append(f"{count} acciones observadas en {'este' if working else 'el último'} turno")
    actions = []
    for action in activity.get('actions', [])[:3]:
        mark = {'ok': '✓', 'error': '!', 'info': '·'}.get(action.get('outcome'), '·')
        actions.append(f"{mark} {action['label']} · hace {time_text(now - action['at'])}")
    report = activity.get('progress') if working else activity.get('final') or activity.get('progress')
    latest = (activity.get('actions') or [{}])[0]
    alert = ''
    if latest.get('outcome') == 'error':
        alert = 'La última herramienta informó un error.' + (' La sesión sigue trabajando.' if working else '')
    return {'state': state, 'activity': '\n'.join(lines), 'actions': '\n'.join(actions),
        'objective': activity.get('objective') or '', 'report': report or '', 'alert': alert,
        'report_title': 'Último avance comunicado' if working or not activity.get('final') else 'Último resultado comunicado'}


def compact_caption(chat, full=True):
    if chat.get('state') != 'working':
        return 'En descanso' if full else 'Zzz'
    phase = (chat.get('activity') or {}).get('phase', '')
    for match, caption in [('Pruebas', 'Validando'), ('Edición', 'Editando'),
        ('Compilación', 'Compilando'), ('Investigación', 'Investigando'),
        ('Exploración', 'Explorando'), ('Git', 'Git'), ('Publicación', 'Publicando'),
        ('Revisión', 'Revisando'), ('Revisando', 'Revisando'), ('Inspección', 'Inspección')]:
        if match in phase:
            return caption
    return 'Analizando' if phase.startswith('Analizando') else 'Trabajando' if full else 'Activo'


class DetailsCard:
    def __init__(self, root, entries, open_chat):
        import tkinter as tk
        self.root, self.entries, self.open_chat = root, entries, open_chat
        self.ident = None
        self.pinned = False
        self.pending = None
        self.leave_pending = None
        self.target = None
        self.signature = None
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title('Codex Float · Detalles')
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.configure(bg='#111925', highlightthickness=1, highlightbackground='#537389')
        self.body = tk.Frame(self.window, bg='#111925', padx=15, pady=12)
        self.body.pack(fill='both', expand=True)
        self.labels = {}
        header = tk.Frame(self.body, bg='#111925')
        header.pack(fill='x')
        tk.Button(header, text='×', command=self.hide, takefocus=False, bg='#111925', fg='#c3d3e5',
            relief='flat', borderwidth=0, width=2, font=('Segoe UI', 11), cursor='hand2').pack(side='right', padx=(8, 0))
        self.pin_button = tk.Button(header, text='Fijar', command=self.toggle_pin, takefocus=False,
            bg='#223347', fg='#c3d3e5', relief='flat', borderwidth=0, width=6, font=('Segoe UI', 8), cursor='hand2')
        self.pin_button.pack(side='right')
        self.labels['project'] = tk.Label(header, bg='#111925', fg='#77e4c8', font=('Segoe UI Semibold', 10),
            anchor='w', justify='left', wraplength=240)
        self.labels['project'].pack(side='left', fill='x', expand=True)
        content = tk.Frame(self.body, bg='#111925')
        content.pack(fill='x')
        content.columnconfigure(0, weight=1)
        for row, (name, color, font) in enumerate([('title', '#eef3fb', ('Segoe UI Semibold', 11)),
            ('state', '#77e4c8', ('Segoe UI', 9)), ('objective_title', '#869bb2', ('Segoe UI', 8)),
            ('objective', '#e0e8f3', ('Segoe UI', 9)), ('activity_title', '#869bb2', ('Segoe UI', 8)),
            ('activity', '#c3d3e5', ('Segoe UI', 9)), ('alert', '#f0bd75', ('Segoe UI', 9)),
            ('actions', '#c3d3e5', ('Segoe UI', 9)),
            ('report_title', '#869bb2', ('Segoe UI', 8)), ('report', '#e0e8f3', ('Segoe UI', 9))]):
            widget = tk.Label(content, bg='#111925', fg=color, font=font, anchor='w',
                justify='left', wraplength=350, borderwidth=0)
            self.labels[name] = widget
            widget.grid(row=row, column=0, sticky='ew', pady=(8 if name.endswith('_title') or name == 'title' else 3, 0))
        tk.Button(self.body, text='Ir a la terminal ↗', command=self.activate, takefocus=False,
            bg='#223347', fg='#d9eee8', activebackground='#34516a', activeforeground='white',
            relief='flat', font=('Segoe UI', 9), cursor='hand2', pady=5).pack(fill='x', pady=(12, 0))
        self.window.bind('<Enter>', lambda event: self.cancel_leave())
        self.window.bind('<Leave>', lambda event: self.leave())
        self.window.bind('<Escape>', lambda event: self.hide())
        self.window.update_idletasks()
        self.no_activate()

    def no_activate(self):
        import ctypes
        from ctypes import wintypes as W
        user = ctypes.windll.user32
        user.GetAncestor.argtypes = [W.HWND, W.UINT]
        user.GetAncestor.restype = W.HWND
        user.GetWindowLongW.argtypes = [W.HWND, ctypes.c_int]
        user.SetWindowLongW.argtypes = [W.HWND, ctypes.c_int, ctypes.c_long]
        hwnd = user.GetAncestor(self.window.winfo_id(), 2)
        style = user.GetWindowLongW(hwnd, -20)
        user.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x80)

    def cancel_leave(self):
        if self.leave_pending:
            self.root.after_cancel(self.leave_pending)
            self.leave_pending = None

    def request(self, ident):
        self.cancel_leave()
        if any(entry.get('drag') for entry in self.entries.values()) or self.pinned or ident == self.ident or ident == self.target:
            return
        self.cancel_request()
        self.target = ident
        self.pending = self.root.after(450, lambda: self.show(ident))

    def cancel_request(self):
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.target = None

    def leave(self):
        self.cancel_leave()
        self.leave_pending = self.root.after(250, self.check_leave)

    def contains_pointer(self, surface):
        x, y = self.root.winfo_pointerxy()
        return (surface.winfo_ismapped() and
            surface.winfo_rootx() <= x < surface.winfo_rootx() + surface.winfo_width() and
            surface.winfo_rooty() <= y < surface.winfo_rooty() + surface.winfo_height())

    def reconcile_pointer(self):
        """Native moves/resizes do not always deliver Tk crossing events."""
        if self.pinned:
            return
        if self.ident and self.contains_pointer(self.window):
            self.cancel_leave()
            return
        for ident, entry in self.entries.items():
            if self.contains_pointer(entry['window']):
                self.request(ident)
                return
        if (self.ident or self.target) and self.leave_pending is None:
            self.leave()

    def check_leave(self):
        self.leave_pending = None
        if self.pinned:
            return
        surfaces = [self.window]
        owner = self.entries.get(self.ident or self.target)
        if owner:
            surfaces.append(owner['window'])
        for surface in surfaces:
            if self.contains_pointer(surface):
                return
        self.hide()

    def show(self, ident, pinned=False):
        self.cancel_request()
        self.cancel_leave()
        if ident not in self.entries:
            return
        if not pinned and not self.contains_pointer(self.entries[ident]['window']):
            return
        self.ident, self.pinned = ident, pinned
        self.signature = None
        self.refresh()
        self.no_activate()
        self.window.deiconify()
        self.window.lift()

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.pin_button.configure(text='Fijada' if self.pinned else 'Fijar')
        if not self.pinned:
            self.leave()

    def hide(self):
        self.cancel_request()
        self.cancel_leave()
        self.ident, self.pinned = None, False
        self.window.withdraw()

    def activate(self):
        ident = self.ident
        self.hide()
        if ident in self.entries:
            self.open_chat(ident)

    def refresh(self):
        if self.ident is None:
            return
        entry = self.entries.get(self.ident)
        if not entry:
            self.hide()
            return
        chat = dict(entry.get('chat') or {})
        chat['minimized'] = entry.get('minimized')
        fields = details_text(chat)
        fields.update(project=safe_preview(chat.get('project') or 'Codex CLI', 60),
            title=safe_preview(chat.get('title', 'Sesión de Codex'), 100),
            objective_title='Objetivo' if fields['objective'] else '', activity_title='Actividad observada')
        if not fields['report']:
            fields['report_title'] = ''
        signature = tuple(fields.items())
        self.pin_button.configure(text='Fijada' if self.pinned else 'Fijar')
        if signature != self.signature:
            self.signature = signature
            for name, label in self.labels.items():
                label.configure(text=fields.get(name, ''))
                if name != 'project':
                    label.grid() if fields.get(name) else label.grid_remove()
        self.window.update_idletasks()
        owner = entry['window']
        from avatar_layout import monitor_work_area
        area = monitor_work_area((owner.winfo_x() + entry['size'][0] // 2,
            owner.winfo_y() + entry['size'][1] // 2))
        location = card_position((owner.winfo_x(), owner.winfo_y(), *entry['size']),
            (382, self.window.winfo_reqheight()), area)
        self.window.geometry(f'382x{self.window.winfo_reqheight()}{location[0]:+d}{location[1]:+d}')
