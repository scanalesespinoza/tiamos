"""Stable companion identities, bounded notices, and code-native expressive sprites."""
import hashlib
import math
from PIL import Image, ImageDraw

COLORS = ('#77e4c8', '#80bfff', '#d3a0ff', '#ffc275', '#ff9bb6', '#c2dd7b', '#80dce8', '#dcb99b')
COLOR_NAMES = ('Menta', 'Azul', 'Lila', 'Ámbar', 'Rosa', 'Lima', 'Turquesa', 'Arena')
ACCESSORIES = ('Antena', 'Auriculares', 'Orejas', 'Gorra')
STATES = ('working', 'reading', 'editing', 'testing', 'waiting', 'error', 'sleeping', 'celebrating', 'greeting', 'carried')


def provider_theme(provider):
    return {'name': 'Claude', 'background': '#dfc2a8', 'foreground': '#75421f'} if provider == 'claude' else {
        'name': 'Codex', 'background': '#b8cce3', 'foreground': '#25496b'}


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
    for step in range(8):
        image = Image.new('RGB', (160, 104), background)
        draw = ImageDraw.Draw(image)
        bounce = round(math.sin(step * math.pi / 4) * (3 if state == 'celebrating' else 1))
        top = 17 + bounce
        draw.rounded_rectangle((29, top, 131, top + 62), radius=12, fill='#2a3447', outline=accent, width=2)
        draw.rounded_rectangle((37, top + 8, 123, top + 49), radius=7, fill='#0d1420')
        if accessory == 0:
            draw.line((80, top, 80, top - 8), fill=accent, width=2)
            draw.ellipse((77, top - 13, 83, top - 7), fill=accent)
        elif accessory == 1:
            draw.arc((23, top - 4, 137, top + 60), 180, 360, fill=accent, width=3)
            draw.rounded_rectangle((22, top + 21, 29, top + 39), radius=3, fill=accent)
            draw.rounded_rectangle((131, top + 21, 138, top + 39), radius=3, fill=accent)
        elif accessory == 2:
            draw.polygon([(49, top), (55, top - 10), (67, top)], fill=accent)
            draw.polygon([(93, top), (105, top - 10), (111, top)], fill=accent)
        else:
            draw.rounded_rectangle((56, top - 7, 106, top + 2), radius=4, fill=accent)
            draw.line((51, top + 2, 117, top + 2), fill=accent, width=3)
        for x in (59, 96):
            if state == 'sleeping':
                draw.arc((x - 2, top + 17, x + 10, top + 28), 0, 180, fill=accent, width=2)
            elif state == 'celebrating':
                draw.line([(x - 2, top + 25), (x + 4, top + 19), (x + 10, top + 25)], fill=accent, width=2)
            else:
                shift = 2 if state == 'reading' and step >= 4 else -1 if state == 'carried' else 0
                draw.rounded_rectangle((x + shift, top + 19, x + 6 + shift, top + 29), radius=2, fill=accent)
        draw.arc((72, top + 32, 89, top + 42), 0, 180, fill=accent, width=2)
        draw.rounded_rectangle((64, top + 62, 96, top + 67), radius=2, fill='#46536b')
        if state in ('working', 'editing'):
            for key in range(5):
                draw.rounded_rectangle((46 + key * 14, 90, 56 + key * 14, 95), radius=2,
                    fill=accent if key == step % 5 else '#46536b')
            if state == 'editing':
                draw.line((126, 71, 142, 88), fill='#ffc275', width=4)
                draw.polygon([(124, 68), (124, 75), (130, 71)], fill='#e9eff7')
        elif state == 'reading':
            draw.polygon([(50, 79), (79, 84), (79, 101), (50, 96)], fill='#344a66', outline=accent)
            draw.polygon([(81, 84), (110, 79), (110, 96), (81, 101)], fill='#344a66', outline=accent)
            draw.ellipse((117, 62, 136, 81), outline=accent, width=3)
            draw.line((134, 79, 143, 89), fill=accent, width=3)
        elif state == 'testing':
            draw.rounded_rectangle((48, 84, 113, 101), radius=4, fill='#0d1420', outline=accent)
            for lamp in range(3):
                draw.ellipse((57 + lamp * 18, 89, 63 + lamp * 18, 95), fill=accent if lamp == step % 3 else '#46536b')
        elif state == 'waiting':
            draw.rectangle((59, 76, 101, 103), fill=background)
            draw.polygon([(62, 78), (98, 78), (98, 81), (84, 90), (98, 99),
                (98, 102), (62, 102), (62, 99), (76, 90), (62, 81)], fill='#0d1420', outline=accent)
            draw.line((60, 77, 100, 77), fill=accent, width=2)
            draw.line((60, 102, 100, 102), fill=accent, width=2)
            draw.polygon([(66 + step, 81 + step // 2), (94 - step, 81 + step // 2), (80, 88)], fill=accent)
            draw.polygon([(65, 99), (95, 99), (80, 98 - step)], fill=accent)
            draw.point((80, 90 + step % 3), fill=accent)
        elif state == 'error':
            draw.line((56, top + 14, 69, top + 18), fill='#ffc275', width=2)
            draw.line((126, 72, 140, 90), fill='#ffc275', width=5)
            draw.arc((118, 61, 133, 77), 30, 300, fill='#ffc275', width=4)
            draw.text((139, 29), '?', fill='#ffc275')
        elif state == 'sleeping':
            for n in range(3):
                draw.text((130 + n * 8, 27 - n * 7 - step // 3), 'z', fill=accent)
        elif state == 'celebrating':
            for n, color in enumerate((accent, '#ffc275', '#ff9bb6', '#80bfff')):
                x = (20 + n * 39 + step * 3) % 154
                y = 4 + (n * 11 + step * 5) % 70
                draw.rectangle((x, y, x + 3, y + 3), fill=color)
        elif state in ('greeting', 'carried'):
            lift = step % 3 * 3
            draw.line((132, top + 39, 145, top + 20 - lift), fill=accent, width=3)
            draw.ellipse((141, top + 11 - lift, 149, top + 20 - lift), outline=accent, width=2)
        frames.append(image)
    return frames
