"""Stable companion identities, bounded notices, and code-native expressive sprites."""
import hashlib
import math
from PIL import Image, ImageDraw, ImageColor
from avatar_theme import palettes

COLORS = ('#77e4c8', '#80bfff', '#d3a0ff', '#ffc275', '#ff9bb6', '#c2dd7b', '#80dce8', '#dcb99b')
COLOR_NAMES = ('Menta', 'Azul', 'Lila', 'Ámbar', 'Rosa', 'Lima', 'Turquesa', 'Arena')
ACCESSORIES = ('Antena', 'Auriculares', 'Orejas', 'Gorra')
STATES = ('working', 'reading', 'editing', 'testing', 'waiting', 'error', 'sleeping', 'celebrating', 'greeting', 'carried')


def provider_theme(provider):
    themes = palettes({})
    return themes.get(provider, themes['codex'])


def identity(ident, registry):
    if ident not in registry:
        start = int.from_bytes(hashlib.sha256(ident.encode()).digest()[:4], 'big') % 32
        used = set(registry.values())
        registry[ident] = next((slot for offset in range(32) if (slot := (start + offset) % 32) not in used), start)
    slot = int(registry[ident]) % 32
    return COLORS[slot % len(COLORS)], slot // len(COLORS)


def customize(ident, registry, color=None, accessory=None, reset=False):
    if reset:
        registry.pop(ident, None)
        return identity(ident, registry)
    current_color, current_accessory = identity(ident, registry)
    color = COLORS.index(current_color) if color is None else color
    accessory = current_accessory if accessory is None else accessory
    if color not in range(len(COLORS)) or accessory not in range(len(ACCESSORIES)):
        raise ValueError('Unknown companion appearance')
    registry[ident] = accessory * len(COLORS) + color
    return identity(ident, registry)


def visual_state(chat, celebrating=False, greeting=False, carried=False):
    if carried:
        return 'carried'
    activity = chat.get('activity') or {}
    if chat.get('state') == 'unknown':
        return 'waiting'
    if chat.get('state') != 'working':
        return 'celebrating' if celebrating else 'greeting' if greeting else 'sleeping'
    latest = (activity.get('actions') or [{}])[0]
    if latest.get('outcome') == 'error':
        return 'error'
    if greeting:
        return 'greeting'
    phase = activity.get('phase', '')
    if 'Edición' in phase:
        return 'editing'
    if 'Pruebas' in phase or 'Compilación' in phase:
        return 'testing'
    if phase.startswith('Esperando'):
        return 'waiting'
    if any(word in phase for word in ('Exploración', 'Investigación', 'Inspección', 'Revisión')):
        return 'reading'
    return 'working'


class Notices:
    def __init__(self, records=None):
        self.records = records or {}
        self.ready = False

    def observe(self, chats, now):
        celebrations = set()
        changed = False
        for chat in chats:
            activity = chat.get('activity') or {}
            finished = activity.get('last_completed_at')
            completion_error = activity.get('last_completion_error', False)
            if not finished and activity.get('phase') == 'Turno finalizado':
                finished = activity.get('finished_at')
                completion_error = (activity.get('actions') or [{}])[0].get('outcome') == 'error'
            if not finished:
                continue
            record = self.records.setdefault(chat['id'], {'completed_at': 0, 'acknowledged_at': 0})
            if finished > record['completed_at']:
                record['completed_at'] = finished
                changed = True
                if self.ready and 0 <= now - finished < 60 and activity.get('phase') == 'Turno finalizado' and not completion_error:
                    celebrations.add(chat['id'])
        self.ready = True
        return changed, celebrations

    def pending(self, ident):
        record = self.records.get(ident, {})
        return record.get('completed_at', 0) > record.get('acknowledged_at', 0)

    def acknowledge(self, ident):
        if not self.pending(ident):
            return False
        self.records[ident]['acknowledged_at'] = self.records[ident]['completed_at']
        return True


def render_frames(state, accent, accessory=0, background='#171d28'):
    frames = []
    rgb = ImageColor.getrgb(accent)
    accessory_shadow = tuple(round(channel * .62) for channel in rgb)
    accessory_light = tuple(round(channel + (255 - channel) * .3) for channel in rgb)
    shadow = tuple(round(channel * .78) for channel in ImageColor.getrgb(background))
    face_glow = tuple(round(channel * .24) for channel in rgb)
    for step in range(8):
        image = Image.new('RGB', (480, 312), background)
        draw = ImageDraw.Draw(image)

        def paint(shape, coordinates, *args, **style):
            # Keep the artwork in logical pixels; rasterize at 3x once per
            # cached frame so curves also stay clean at the compact size.
            if isinstance(coordinates[0], (tuple, list)):
                coordinates = [(x * 3, y * 3) for x, y in coordinates]
            else:
                coordinates = tuple(value * 3 for value in coordinates)
            for key in ('width', 'radius'):
                if key in style:
                    style[key] *= 3
            getattr(draw, shape)(coordinates, *args, **style)

        bounce = round(math.sin(step * math.pi / 4) * (3 if state == 'celebrating' else 1))
        top = 17 + bounce
        paint('ellipse', (39, 93, 121, 101), fill=shadow)
        paint('rounded_rectangle', (29, top + 3, 132, top + 65), radius=15, fill='#101827')
        paint('rounded_rectangle', (29, top, 131, top + 62), radius=14, fill=accessory_shadow, outline='#101827', width=1)
        paint('rounded_rectangle', (30, top, 130, top + 59), radius=13, fill='#3c4c63', outline=accent, width=1)
        paint('rounded_rectangle', (33, top + 3, 127, top + 56), radius=11, fill='#29374c')
        paint('line', (45, top + 3, 115, top + 3), fill=accessory_light, width=1)
        paint('rounded_rectangle', (36, top + 7, 124, top + 50), radius=10, fill='#080f1b', outline='#52647b', width=1)
        paint('rounded_rectangle', (39, top + 10, 121, top + 47), radius=8, fill='#101c2d')
        paint('line', (48, top + 12, 94, top + 12), fill='#22364b', width=1)
        paint('line', (98, top + 12, 107, top + 12), fill='#22364b', width=1)
        for x in (44, 111):
            paint('ellipse', (x, top + 33, x + 6, top + 36), fill=face_glow)
        for x in (47, 51, 55):
            paint('line', (x, top + 54, x, top + 56), fill='#65778f', width=1)
        paint('rounded_rectangle', (104, top + 54, 113, top + 56), radius=1, fill=accessory_shadow)
        paint('ellipse', (115, top + 53, 118, top + 56), fill=accent)
        if accessory == 0:
            paint('rounded_rectangle', (72, top - 1, 88, top + 4), radius=3,
                                   fill=accessory_shadow, outline='#152033')
            paint('line', (80, top + 1, 80, top - 6), fill='#152033', width=5)
            paint('line', (80, top, 80, top - 6), fill=accent, width=3)
            paint('ellipse', (74, top - 14, 86, top - 3), fill=accessory_shadow, outline='#152033')
            paint('ellipse', (75, top - 13, 84, top - 5), fill=accent)
            paint('ellipse', (77, top - 12, 80, top - 10), fill=accessory_light)
        elif accessory == 1:
            paint('arc', (19, top - 12, 141, top + 70), 180, 360, fill='#152033', width=9)
            paint('arc', (21, top - 10, 139, top + 68), 180, 360, fill=accessory_shadow, width=5)
            paint('arc', (23, top - 9, 137, top + 65), 205, 335, fill=accent, width=3)
            for left in (15, 129):
                paint('rounded_rectangle', (left, top + 19, left + 16, top + 45), radius=5,
                                       fill=accessory_shadow, outline=accent, width=2)
            paint('rounded_rectangle', (26, top + 23, 33, top + 42), radius=3, fill='#111925', outline='#46536b')
            paint('rounded_rectangle', (127, top + 23, 134, top + 42), radius=3, fill='#111925', outline='#46536b')
            paint('line', (19, top + 25, 19, top + 37), fill=accessory_light, width=2)
            paint('line', (141, top + 25, 141, top + 37), fill=accessory_light, width=2)
        elif accessory == 2:
            for mirrored in (False, True):
                def ear_points(points):
                    return [(160 - x if mirrored else x, top + y) for x, y in points]
                paint('polygon', ear_points([(42, 4), (46, -13), (68, 4)]),
                             fill=accessory_shadow, outline='#152033')
                paint('line', ear_points([(43, 3), (47, -11), (65, 3)]), fill=accent, width=2)
                paint('polygon', ear_points([(49, -6), (48, 1), (59, 1)]), fill=accessory_light)
        else:
            # A rounded crown and a forward visor stay distinct at half size.
            # The top button fits even at the celebration's highest bounce.
            paint('ellipse', (76, top - 14, 82, top - 10), fill=accessory_shadow, outline='#152033')
            paint('pieslice', (49, top - 12, 110, top + 15), 180, 360,
                          fill=accessory_shadow, outline='#152033', width=1)
            paint('polygon', [(50, top + 2), (52, top - 4), (59, top - 9),
                          (69, top - 11), (81, top - 11), (86, top + 2)], fill=accent)
            paint('line', [(81, top - 10), (85, top - 5), (87, top + 1)], fill=accessory_light, width=1)
            paint('ellipse', (65, top - 6, 73, top + 1), fill='#243447', outline=accessory_light)
            paint('polygon', [(49, top + 2), (103, top + 2), (118, top + 6),
                          (124, top + 10), (114, top + 12), (89, top + 9),
                          (68, top + 7), (49, top + 7)], fill=accessory_shadow, outline='#152033')
            paint('line', [(52, top + 3), (101, top + 3), (116, top + 7),
                       (120, top + 9)], fill=accent, width=2)
        for x in (58, 95):
            if state == 'sleeping':
                paint('arc', (x - 2, top + 17, x + 11, top + 29), 0, 180, fill=accent, width=2)
            elif state == 'celebrating':
                paint('line', [(x - 2, top + 26), (x + 4, top + 20), (x + 11, top + 26)], fill=accent, width=2)
            elif step == 6 and state in ('working', 'editing', 'reading', 'greeting'):
                paint('line', (x, top + 25, x + 8, top + 25), fill=accent, width=2)
            else:
                shift = 2 if state == 'reading' and step >= 4 else -1 if state == 'carried' else 0
                paint('rounded_rectangle', (x + shift, top + 19, x + 8 + shift, top + 31), radius=4, fill=accent)
                paint('rounded_rectangle', (x + 1 + shift, top + 20, x + 4 + shift, top + 24), radius=1, fill=accessory_light)
        if state in ('sleeping', 'carried'):
            paint('ellipse', (77, top + 36, 83, top + 42), outline=accent, width=1)
        elif state in ('waiting', 'error'):
            paint('line', (75, top + 39, 86, top + 39), fill=accent, width=2)
        else:
            paint('arc', (72, top + 32, 89, top + 42), 0, 180, fill=accent, width=2)
        paint('rounded_rectangle', (68, top + 62, 92, top + 68), radius=2, fill='#1b283b')
        paint('rounded_rectangle', (61, top + 66, 99, top + 70), radius=2, fill='#536780')
        paint('line', (65, top + 66, 95, top + 66), fill='#8494a9', width=1)
        if state in ('working', 'editing'):
            paint('rounded_rectangle', (41, 86, 119, 99), radius=4, fill='#142033', outline='#52647b', width=1)
            for key in range(5):
                paint('rounded_rectangle', (46 + key * 14, 90, 56 + key * 14, 95), radius=2,
                    fill=accent if key == step % 5 else '#64758b')
            if state == 'editing':
                paint('line', (126, 71, 142, 88), fill='#ffc275', width=4)
                paint('polygon', [(124, 68), (124, 75), (130, 71)], fill='#e9eff7')
        elif state == 'reading':
            paint('polygon', [(50, 79), (79, 84), (79, 101), (50, 96)], fill='#344a66', outline=accent)
            paint('polygon', [(81, 84), (110, 79), (110, 96), (81, 101)], fill='#344a66', outline=accent)
            for y in (85, 89, 93):
                paint('line', (55, y, 74, y + 3), fill='#91a5bd', width=1)
                paint('line', (86, y + 3, 105, y), fill='#91a5bd', width=1)
            paint('ellipse', (117, 62, 136, 81), outline=accent, width=3)
            paint('line', (134, 79, 143, 89), fill=accent, width=3)
        elif state == 'testing':
            paint('rounded_rectangle', (48, 84, 113, 101), radius=4, fill='#0d1420', outline=accent)
            for lamp in range(3):
                paint('ellipse', (57 + lamp * 18, 89, 63 + lamp * 18, 95), fill=accent if lamp == step % 3 else '#46536b')
        elif state == 'waiting':
            paint('rectangle', (59, 76, 101, 103), fill=background)
            paint('polygon', [(62, 78), (98, 78), (98, 81), (84, 90), (98, 99),
                (98, 102), (62, 102), (62, 99), (76, 90), (62, 81)], fill='#0d1420', outline=accent)
            paint('line', (60, 77, 100, 77), fill=accent, width=2)
            paint('line', (60, 102, 100, 102), fill=accent, width=2)
            paint('polygon', [(66 + step, 81 + step // 2), (94 - step, 81 + step // 2), (80, 88)], fill=accent)
            paint('polygon', [(65, 99), (95, 99), (80, 98 - step)], fill=accent)
            paint('point', (80, 90 + step % 3), fill=accent)
        elif state == 'error':
            paint('line', (56, top + 14, 69, top + 18), fill='#ffc275', width=2)
            paint('line', (126, 72, 140, 90), fill='#ffc275', width=5)
            paint('arc', (118, 61, 133, 77), 30, 300, fill='#ffc275', width=4)
            paint('arc', (139, 28, 146, 35), 185, 390, fill='#ffc275', width=1)
            paint('line', (142, 35, 142, 38), fill='#ffc275', width=1)
            paint('ellipse', (141, 41, 143, 43), fill='#ffc275')
        elif state == 'sleeping':
            for n in range(3):
                x, y = 132 + n * 8, 29 - n * 8 - step // 3
                paint('line', [(x, y), (x + 5, y), (x, y + 5), (x + 5, y + 5)], fill=accent, width=1)
        elif state == 'celebrating':
            for n, color in enumerate((accent, '#ffc275', '#ff9bb6', '#80bfff')):
                x = (20 + n * 39 + step * 3) % 154
                y = 4 + (n * 11 + step * 5) % 70
                paint('rectangle', (x, y, x + 3, y + 3), fill=color)
        elif state in ('greeting', 'carried'):
            lift = step % 3 * 3
            paint('line', (132, top + 39, 145, top + 20 - lift), fill=accent, width=3)
            paint('ellipse', (141, top + 11 - lift, 149, top + 20 - lift), outline=accent, width=2)
        frames.append(image.resize((160, 104), Image.Resampling.LANCZOS))
    return frames
