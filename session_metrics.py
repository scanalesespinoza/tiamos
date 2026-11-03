"""Small numeric aggregates from the existing incremental activity reader."""
from collections import deque
import datetime as dt
from math import isqrt

FIELDS = ('xp', 'actions', 'ok', 'errors', 'unknown', 'waits', 'api_errors',
          'validations', 'validations_ok', 'edits', 'completed', 'interrupted',
          'completed_seconds', 'timed_turns')
ACTION_XP_LIMIT = 50


def empty_counts():
    return dict.fromkeys(FIELDS, 0)


def level_progress(xp):
    # Level L starts at 50 * L * (L - 1): 0, 100, 300, 600, ...
    xp = max(0, int(xp))
    level = (1 + isqrt(1 + 4 * (xp // 50))) // 2
    start = 50 * level * (level - 1)
    needed = 100 * level
    return {'level': level, 'xp': xp, 'progress': xp - start, 'needed': needed}


class SessionMetrics:
    def __init__(self):
        self.total = empty_counts()
        self.days = {}
        self.active = False
        self.started_at = None
        self.turn_key = None
        self.recent_turns = deque(maxlen=256)
        self.action_xp = 0

    def bump(self, stamp, **values):
        day = stamp.astimezone().date().isoformat()
        daily = self.days.setdefault(day, empty_counts())
        for key, value in values.items():
            self.total[key] += value
            daily[key] += value
        # Total survives; only eight local calendar buckets are needed in memory.
        if len(self.days) > 8:
            del self.days[min(self.days)]

    def start(self, stamp, turn=None):
        key = turn or stamp.timestamp()
        if key in self.recent_turns:
            return
        self.recent_turns.append(key)
        self.active = True
        self.started_at = stamp.timestamp()
        self.turn_key = turn
        self.action_xp = 0

    def action(self, label, outcome, stamp):
        if not self.active:
            return
        if label.startswith('Esperando'):
            self.bump(stamp, waits=1)
            return
        if label == 'Error de Claude':
            self.bump(stamp, api_errors=1)
            return
        outcome_key = {'ok': 'ok', 'error': 'errors'}.get(outcome, 'unknown')
        counts = {'actions': 1, outcome_key: 1}
        validation = label in ('Pruebas y validación', 'Compilación')
        if validation:
            counts.update(validations=1, validations_ok=int(outcome == 'ok'))
        if label == 'Edición de archivos':
            counts['edits'] = 1
        earned = 2 + 3 * validation if outcome == 'ok' else 1 if outcome == 'info' else 0
        earned = min(earned, ACTION_XP_LIMIT - self.action_xp) if self.active else 0
        self.action_xp += earned
        self.bump(stamp, xp=earned, **counts)

    def finish(self, stamp, completed, turn=None):
        if not self.active or (turn and self.turn_key and turn != self.turn_key):
            return
        self.active = False
        if completed:
            elapsed = stamp.timestamp() - self.started_at
            counts = {'completed': 1, 'xp': 10}
            if elapsed >= 0:
                counts.update(completed_seconds=round(elapsed, 3), timed_turns=1)
            self.bump(stamp, **counts)
        else:
            self.bump(stamp, interrupted=1)

    def summary(self, now=None):
        now = now or dt.datetime.now().astimezone()
        day = now.astimezone().date().isoformat()
        return {**level_progress(self.total['xp']), 'day': day,
                'total': dict(self.total), 'today': dict(self.days.get(day, empty_counts()))}


def profile_text(stats):
    if not stats:
        return {'profile_level': 'Nivel 1 · sin datos todavía',
                'profile_note': 'Las estadísticas aparecerán al observar actividad.'}
    today, total = stats['today'], stats['total']
    known = today['ok'] + today['errors']
    rate = f"{today['ok'] / known:.0%} ({today['ok']}/{known})" if known else 'sin resultados conocidos'
    average = ''
    if total['timed_turns']:
        # Wall-clock turn duration includes waits; it is not compute time.
        from session_activity import time_text
        average = '\nDuración media de turno: ' + time_text(total['completed_seconds'] / total['timed_turns'])
    return {
        'profile_level': f"Nivel {stats['level']} · {stats['xp']:,} XP acumulada\n"
                         f"{stats['progress']}/{stats['needed']} XP → nivel {stats['level'] + 1}",
        'profile_today': f"Hoy · +{today['xp']} XP · {today['actions']} acciones\n"
                         f"✓ {today['ok']} éxitos · ! {today['errors']} errores · {today['unknown']} sin resultado\n"
                         f"{today['completed']} turnos finalizados · {today['interrupted']} interrumpidos",
        'profile_quality': f"Herramientas OK hoy: {rate}\n"
                           f"Validaciones OK: {today['validations_ok']}/{today['validations']} · Ediciones: {today['edits']}\n"
                           f"Esperas: {today['waits']} · Errores de API: {today['api_errors']}",
        'profile_history': f"Historial disponible · {total['actions']} acciones\n"
                           f"✓ {total['ok']} éxitos · ! {total['errors']} errores · {total['unknown']} sin resultado\n"
                           f"{total['completed']} turnos finalizados · {total['interrupted']} interrumpidos" + average,
        'profile_note': 'Un éxito de herramienta no certifica la tarea.\n'
                        'XP limitada por turno; duración incluye esperas.',
    }
