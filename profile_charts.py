"""Bounded native Tk drawings; no chart dependency, timer, or transcript access."""
from session_metrics import AREAS

BACKGROUND = '#111925'
MUTED = '#869bb2'
INK = '#e0e8f3'
GOOD = '#77e4c8'
CAUTION = '#f0bd75'


def chart_data(stats):
    stats = stats or {}
    turns = stats.get('progression', [])[-7:]
    change = None
    if len(turns) >= 6:
        before, after = turns[-6:-3], turns[-3:]
        old_ok, new_ok = sum(t['ok'] for t in before), sum(t['ok'] for t in after)
        old_n = sum(t['ok'] + t['errors'] for t in before)
        new_n = sum(t['ok'] + t['errors'] for t in after)
        if min(old_n, new_n) >= 5:
            change = {'points': round(100 * (new_ok / new_n - old_ok / old_n)),
                      'before': (old_ok, old_n), 'after': (new_ok, new_n)}
    areas = []
    for key, label in AREAS.items():
        counts = stats.get('areas', {}).get(key, {})
        known = counts.get('ok', 0) + counts.get('errors', 0)
        areas.append({'key': key, 'label': label, 'known': known, 'ok': counts.get('ok', 0),
                      'unknown': counts.get('unknown', 0),
                      'rate': counts.get('ok', 0) / known if known else None})
    eligible = [area['rate'] for area in areas if area['known'] >= 5]
    best = max(eligible) if eligible else None
    for area in areas:
        area['best'] = best is not None and best > 0 and area['known'] >= 5 and area['rate'] == best
    return {'turns': turns, 'change': change, 'areas': areas}


class ProfileChart:
    def __init__(self, parent):
        import tkinter as tk
        self.canvas = tk.Canvas(parent, width=350, height=238, bg=BACKGROUND,
                                highlightthickness=0, borderwidth=0)
        self.signature = None
        self.redraws = 0

    def update(self, stats, accent=GOOD):
        data = chart_data(stats)
        signature = (repr(data), accent)
        if signature == self.signature:
            return
        self.signature = signature
        self.redraws += 1
        c = self.canvas
        c.delete('all')

        def text(x, y, value, color=INK, anchor='w', size=8):
            c.create_text(x, y, text=value, fill=color, font=('Segoe UI', size), anchor=anchor)

        text(0, 9, 'Crecimiento · XP al cerrar cada turno')
        turns = data['turns']
        if turns:
            values = [t['xp'] for t in turns]
            low, high = min(values), max(values)
            span = max(1, high - low)
            # A single observed turn is one point, never an invented upward line.
            points = [(48 + i * 270 / max(1, len(turns) - 1),
                       43 if high == low else 57 - (t['xp'] - low) * 29 / span) for i, t in enumerate(turns)]
            c.create_line(28, 63, 320, 63, fill='#344456')
            if len(points) > 1:
                c.create_line(*[v for point in points for v in point], fill=accent, width=2)
            for (x, y), turn in zip(points, turns):
                c.create_oval(x - 3, y - 3, x + 3, y + 3,
                              fill=accent if turn['completed'] else CAUTION, outline='')
            text(0, 43 if high == low else 29, str(high), MUTED, size=7)
            if high != low:
                text(0, 57, str(low), MUTED, size=7)
            text(28, 73, f"Últimos {len(turns)} turnos · ámbar = interrumpido", MUTED, size=7)
        else:
            text(175, 46, 'La curva aparecerá al cerrar el primer turno.', MUTED, anchor='center')
        change = data['change']
        if change:
            old_ok, old_n = change['before']
            new_ok, new_n = change['after']
            pp = change['points']
            text(0, 95, f"OK: {pp:+d} pp · {old_ok}/{old_n} → {new_ok}/{new_n}",
                 GOOD if pp > 0 else CAUTION if pp < 0 else MUTED)
            text(0, 109, 'Últimos 3 turnos frente a los 3 anteriores', MUTED, size=7)
        else:
            text(0, 95, 'Tendencia OK: aún sin muestra suficiente', MUTED)
            text(0, 109, 'Requiere 6 cierres y ≥5 resultados en cada grupo de 3', MUTED, size=7)
        text(0, 130, 'Áreas · éxitos / resultados conocidos')
        for i, area in enumerate(data['areas']):
            y = 150 + i * 16
            text(0, y, ('★ ' if area['best'] else '') + area['label'], accent if area['best'] else INK)
            c.create_rectangle(112, y - 3, 222, y + 3, fill='#344456', outline='')
            if area['rate']:
                c.create_rectangle(112, y - 3, 112 + 110 * area['rate'], y + 3,
                                   fill=accent if area['best'] else '#537389', outline='')
            value = f"{area['rate']:.0%} · {area['ok']}/{area['known']}" if area['known'] else 'Sin resultados'
            text(230, y, value, MUTED, size=7)
        text(0, 231, '★ Mayor tasa con ≥5 resultados · ver desconocidos en Cifras', MUTED, size=7)
