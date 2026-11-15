"""Persistent user-selected markers, drawn only for starred companions."""
import math
import os

SYMBOLS = (('star', 'Estrella'), ('circle', 'Círculo'), ('diamond', 'Rombo'),
           ('triangle', 'Triángulo'), ('square', 'Cuadrado'), ('hexagon', 'Hexágono'))
SYMBOL_KEYS = {key for key, _ in SYMBOLS}
GAP = 4


def preferences(document):
    if not isinstance(document, dict):
        return {}
    return {ident: {'enabled': record.get('enabled') is True,
                    'symbol': record.get('symbol') if record.get('symbol') in SYMBOL_KEYS else 'star'}
            for ident, record in document.items() if isinstance(ident, str) and isinstance(record, dict)
            and isinstance(record.get('symbol', 'star'), str)}


def marker_size(size):
    return 18 if size[0] >= 178 else 14


def footprint(size, anchor, marked):
    width, height = size
    extent = marker_size(size) + GAP if marked else 0
    return (width, height + extent) if anchor in ('top', 'bottom') else (width + extent, height)


def avatar_origin(x, y, size, anchor, marked):
    return (x + marker_size(size) + GAP if marked and anchor == 'right' else x,
            y + marker_size(size) + GAP if marked and anchor == 'bottom' else y)


def occupied_rect(rect, anchor, marked):
    x, y, width, height = rect
    extent = marker_size((width, height)) + GAP if marked and anchor == 'right' else 0
    vertical = marker_size((width, height)) + GAP if marked and anchor == 'bottom' else 0
    return (x - extent, y - vertical, *footprint((width, height), anchor, marked))


def marker_rect(rect, anchor):
    x, y, width, height = rect
    size = marker_size((width, height))
    if anchor in ('top', 'bottom'):
        return x + (width - size) // 2, y - size - GAP if anchor == 'bottom' else y + height + GAP, size, size
    return (x - size - GAP if anchor == 'right' else x + width + GAP,
            y + (height - size) // 2, size, size)


def draw_symbol(canvas, symbol, size):
    """Use native geometry rather than platform-dependent Unicode glyphs."""
    canvas.delete('symbol')
    options = dict(fill='#f1c46b', outline='#8f682c', width=1, tags='symbol')
    if symbol == 'circle':
        return canvas.create_oval(2, 2, size - 2, size - 2, **options)
    if symbol == 'square':
        return canvas.create_rectangle(2, 2, size - 2, size - 2, **options)
    sides = {'star': 10, 'diamond': 4, 'triangle': 3, 'hexagon': 6}[symbol]
    center, radius = size / 2, (size - 3) / 2
    points = []
    for index in range(sides):
        angle = -math.pi / 2 + 2 * math.pi * index / sides
        length = radius * .45 if symbol == 'star' and index % 2 else radius
        points.extend((center + length * math.cos(angle), center + length * math.sin(angle)))
    return canvas.create_polygon(*points, **options)


class StarredMenu:
    def __init__(self, parent, record, on_change):
        import tkinter as tk
        self.enabled = tk.BooleanVar(master=parent, value=record.get('enabled', False))
        self.symbol = tk.StringVar(master=parent, value=record.get('symbol', 'star'))
        self.on_change = on_change
        self.menu = tk.Menu(parent, tearoff=False)
        self.menu.add_checkbutton(label='Destacar avatar', variable=self.enabled, command=self.save)
        self.menu.add_separator()
        for key, label in SYMBOLS:
            self.menu.add_radiobutton(label=label, variable=self.symbol, value=key, command=self.choose_symbol)

    def choose_symbol(self):
        self.enabled.set(True)
        self.save()

    def save(self):
        self.on_change({'enabled': self.enabled.get(), 'symbol': self.symbol.get()})


class StarredMarker:
    def __init__(self, root, on_menu, on_open):
        self.root, self.on_menu, self.on_open = root, on_menu, on_open
        self.window = self.canvas = None
        self.signature = self.geometry = None

    def hide(self):
        if self.window is not None and self.window.state() != 'withdrawn':
            self.window.withdraw()

    def destroy(self):
        if self.window is not None:
            self.window.destroy()
        self.window = self.canvas = None
        self.signature = self.geometry = None

    def status(self):
        if self.window is None:
            return {'visible': False, 'position': None, 'size': None}
        return {'visible': self.window.state() != 'withdrawn',
                'position': [self.window.winfo_x(), self.window.winfo_y()],
                'size': self.signature[1] if self.signature else None}

    def sync(self, rect, anchor, symbol, visible=True, background='#263447'):
        if symbol not in SYMBOL_KEYS:
            self.destroy()
            return
        if not visible:
            self.hide()
            return
        if self.window is None:
            import tkinter as tk
            # Independent of the terminal/companion window's minimize state.
            self.window = tk.Toplevel(self.root)
            self.window.withdraw()
            self.window.title('tiamos · Starred')
            self.window.overrideredirect(True)
            if os.name == 'nt':
                self.window.attributes('-toolwindow', True)
            self.window.attributes('-topmost', True)
            self.canvas = tk.Canvas(self.window, highlightthickness=0, borderwidth=0, cursor='hand2')
            self.canvas.pack(fill='both', expand=True)
            self.canvas.bind('<Button-3>', self.on_menu)
            self.canvas.bind('<Double-Button-1>', lambda _: self.on_open())
        x, y, size, _ = marker_rect(rect, anchor)
        signature = symbol, size, background
        appearance_changed = signature != self.signature
        if appearance_changed:
            color = '#ff00ff' if os.name == 'nt' else background
            self.window.configure(bg=color)
            self.canvas.configure(bg=color, width=size, height=size)
            if os.name == 'nt':
                self.window.attributes('-transparentcolor', color)
            draw_symbol(self.canvas, symbol, size)
            self.signature = signature
        geometry = f'{size}x{size}{x:+d}{y:+d}'
        if geometry != self.geometry:
            self.window.geometry(geometry)
            self.geometry = geometry
        if appearance_changed or self.window.state() == 'withdrawn':
            # Tk can rebuild the native wrapper when transparency changes.
            # Apply non-activation after those attributes, before showing it.
            from session_details import DetailsCard
            self.window.update_idletasks()
            DetailsCard.no_activate(self)
        if self.window.state() == 'withdrawn':
            self.window.deiconify()
