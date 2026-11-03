"""Bounded, privacy-conscious summaries of observable session events."""
from collections import deque
import json
import re
import unicodedata


def text_content(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ''
    return ' '.join(item.get('text', '') for item in content
        if isinstance(item, dict) and str(item.get('type', '')).lower() in {'text', 'input_text', 'output_text'}
        and isinstance(item.get('text'), str))


def safe_preview(text, limit=180):
    """Preview prose only; omit credential-bearing messages rather than echo them."""
    text = unicodedata.normalize('NFKC', str(text))
    if re.search(r'(?i)\b(password|passwd|contrase[nñ]a|secret|token|authorization|bearer|api[_ -]?key)\b|(?:^|\s)-p\s+\S+|\b(?:sk-|gh[pousr]_|glpat-)[A-Za-z0-9_-]+|-----BEGIN', text):
        return 'Contenido sensible omitido. Consulta la terminal.'
    text = re.sub(r'```[\s\S]*?(?:```|$)', '[código omitido]', text)
    text = re.sub(r'`[^`\n]+`', '[código]', text)
    text = re.sub(r'https?://\S+', '[enlace]', text)
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[correo]', text)
    text = re.sub(r'(["\'])(?:[A-Za-z]:[\\/]|/(?:home|Users|tmp|var)/)[^"\']+\1', '[ruta]', text)
    text = re.sub(r'(?:[A-Za-z]:[\\/]|/(?:home|Users|tmp|var)/)\S+', '[ruta]', text)
    text = re.sub(r'\b[A-Za-z0-9_+/=-]{32,}\b', '[identificador]', text)
    text = ''.join(character for character in text if character.isprintable() or character.isspace())
    text = ' '.join(text.replace('```', '').split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def is_control_request(text):
    text = text.strip()
    return bool(re.match(r'(?i)^(?:<environment_context>|<skill>|# AGENTS\.md|These AGENTS\.md|\$[\w-]+\s*$|/?loop(?:\s+and\s+continue\b|\s+\d+[smhd]\b|\s*$)|(?:continue|contin[uú]a|resume|sigue)(?:\s+(?:for|por|durante)\s+\d+.*)?[.!]?\s*$|(?:ok|yes|si|sí|gracias|thanks)[.!]?\s*$)', text))


def category(command='', tool=''):
    """Return a fixed label, never a fragment of a command or its arguments."""
    name = str(tool).lower()
    source = str(command).lower()
    if 'apply_patch' in name or 'apply_patch' in source:
        return 'Edición de archivos'
    if re.search(r'\b(pytest|unittest)\b|\b(cargo|npm|pnpm|yarn|mvn|gradle)\s+(?:run\s+)?test\b', source):
        return 'Pruebas y validación'
    if re.search(r'\bgit\s+push\b|\bgh\s+(pr|issue|release)\s+(create|merge|edit|close)\b', source):
        return 'Publicación y revisión'
    if re.search(r'\bgit\s+(fetch|pull|merge|rebase)\b', source):
        return 'Sincronización Git'
    if re.search(r'\bgit\s+(status|diff|log|show|branch)\b|\bgh\s+(pr|run)\s+(view|checks|list|watch)\b', source):
        return 'Revisión de cambios'
    if re.search(r'\b(cargo|npm|pnpm|yarn)\s+(?:run\s+)?build\b|\bpy_compile\b|\bmvn\s+package\b', source):
        return 'Compilación'
    if 'web' in name or 'search' in name or 'web__run' in source:
        return 'Investigación'
    if 'view_image' in name or 'image' in name or 'screenshot' in name:
        return 'Inspección visual'
    if re.search(r'\b(get-content|get-childitem|rg|find|cat|ls)\b', source) or 'read' in name:
        return 'Exploración de archivos'
    return 'Uso de herramientas'


def time_text(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f'{seconds} s'
    if seconds < 3600:
        return f'{seconds // 60} min {seconds % 60:02d} s'
    return f'{seconds // 3600} h {(seconds % 3600) // 60:02d} min'


class Activity:
    def __init__(self):
        self.objective = ''
        self.progress = ''
        self.final = ''
        self.phase = 'En espera'
        self.started_at = None
        self.finished_at = None
        self.updated_at = None
        self.actions = deque(maxlen=4)
        self.seen = deque(maxlen=256)
        self.count = 0
        self.turn_id = None

    def add_action(self, label, stamp, outcome='info', ident=None):
        if ident and ident in self.seen:
            return
        if ident:
            self.seen.append(ident)
        self.actions.appendleft({'label': label, 'at': stamp.timestamp(), 'outcome': outcome})
        self.count += 1
        self.updated_at = stamp.timestamp()

    def observe(self, record, stamp):
        payload = record.get('payload', {})
        kind = record.get('type')
        event = payload.get('type')
        if kind == 'event_msg':
            turn = payload.get('turn_id') or payload.get('task_id')
            if event == 'task_started':
                self.started_at = stamp.timestamp()
                self.finished_at = None
                self.turn_id = turn
                self.phase = 'Analizando la solicitud'
                self.progress = self.final = ''
                self.actions.clear()
                self.seen.clear()
                self.count = 0
                self.updated_at = stamp.timestamp()
            elif event in {'task_complete', 'task_completed', 'turn_aborted', 'task_aborted', 'task_interrupted', 'turn_cancelled', 'session_end'}:
                if turn and self.turn_id and turn != self.turn_id:
                    return
                self.finished_at = stamp.timestamp()
                self.phase = 'Turno finalizado' if event in {'task_complete', 'task_completed'} else 'Turno interrumpido'
                self.updated_at = stamp.timestamp()
            elif event == 'user_message':
                message = payload.get('message', '')
                if isinstance(message, str) and not is_control_request(message):
                    self.objective = safe_preview(message)
                    self.updated_at = stamp.timestamp()
            elif event == 'item_completed':
                item = payload.get('item', {})
                if not isinstance(item, dict):
                    return
                item_kind = item.get('type', '')
                if item_kind == 'UserMessage':
                    text = text_content(item.get('content'))
                    if text and not is_control_request(text):
                        self.objective = safe_preview(text)
                        self.updated_at = stamp.timestamp()
                elif item_kind == 'AgentMessage':
                    text = safe_preview(text_content(item.get('content')))
                    if item.get('phase') == 'commentary':
                        self.progress = text
                    elif item.get('phase') == 'final':
                        self.final = text
                    self.updated_at = stamp.timestamp()
                elif item_kind in {'CommandExecution', 'FileChange', 'McpToolCall', 'ImageView', 'Extension'}:
                    label = {'FileChange': 'Edición de archivos', 'ImageView': 'Inspección visual', 'Extension': 'Investigación'}.get(item_kind)
                    label = label or category(item.get('command', ''), item.get('tool', ''))
                    code = item.get('exit_code')
                    outcome = 'error' if (code is not None and code != 0) or str(item.get('status', '')).lower() == 'failed' else 'ok' if code == 0 or str(item.get('status', '')).lower() == 'completed' else 'info'
                    self.add_action(label, stamp, outcome, item.get('id'))
                    self.phase = 'Revisando resultados'
        elif kind == 'response_item':
            if event in {'function_call', 'custom_tool_call'}:
                arguments = payload.get('arguments', payload.get('input', ''))
                try:
                    parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                except (ValueError, TypeError):
                    parsed = None
                command = parsed.get('cmd', parsed.get('command', '')) if isinstance(parsed, dict) else arguments
                self.phase = category(command, payload.get('name', ''))
                self.updated_at = stamp.timestamp()
            elif event == 'reasoning':
                # Observe only the event type, never reasoning text or summaries.
                self.phase = 'Analizando'
                self.updated_at = stamp.timestamp()

    def summary(self):
        return {'objective': self.objective, 'progress': self.progress, 'final': self.final,
            'phase': self.phase, 'started_at': self.started_at, 'finished_at': self.finished_at,
            'updated_at': self.updated_at, 'action_count': self.count, 'actions': list(self.actions)}
