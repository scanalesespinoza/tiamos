"""Shared interpretation of explicit session evidence, without time heuristics."""
import math

LABELS = {
    'unavailable': ('Sin conexión', 'Sin conexión'),
    'unknown': ('Sin estado disponible', 'Sin estado'),
    'closed': ('CLI cerrado', 'CLI cerrado'),
    'input': ('Necesita tu respuesta', 'Tu respuesta'),
    'tool_wait': ('Esperando herramienta', 'Herramienta'),
    'working': ('Trabajando', 'Activo'),
    'interrupted': ('Turno interrumpido', 'Interrumpido'),
    'completed': ('Turno terminado', 'Terminado'),
    'resting': ('En descanso', 'Zzz'),
}


def status_code(chat):
    if chat.get('unavailable'):
        return 'unavailable'
    if (chat.get('terminal') or {}).get('live') is False:
        return 'closed'
    state = chat.get('state')
    if state not in ('working', 'sleeping'):
        return 'unknown'
    activity = chat.get('activity') or {}
    phase = activity.get('phase')
    if state == 'working':
        if phase == 'Esperando intervención':
            return 'input'
        if phase == 'Esperando una herramienta':
            return 'tool_wait'
        return 'working'
    finished = activity.get('finished_at')
    if isinstance(finished, (int, float)) and not isinstance(finished, bool) and math.isfinite(finished) and finished > 0:
        if phase == 'Turno interrumpido':
            return 'interrupted'
        if phase == 'Turno finalizado':
            return 'completed'
    return 'resting'


def needs_input(chat):
    return status_code(chat) == 'input'


def status_label(chat, full=True):
    return LABELS[status_code(chat)][0 if full else 1]
