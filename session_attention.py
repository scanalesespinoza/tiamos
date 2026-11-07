"""Bounded attention metadata, independent of Tk and transcript readers."""
import math
import re

from session_activity import safe_preview, time_text

LIMIT = 128
FIELDS = ('error_at', 'error_seen', 'interrupted_at', 'interrupted_seen')
REASONS = {'input': 'Necesita tu respuesta', 'interrupted': 'Turno interrumpido',
           'error': 'Error de herramienta observado', 'result': 'Resultado por revisar'}
ORDER = {kind: index for index, kind in enumerate(REASONS)}


def timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
        return float(value)
    return 0.0


def needs_input(chat):
    """Only explicit provider evidence means a person is needed."""
    return (not chat.get('unavailable') and chat.get('state') == 'working'
            and (chat.get('activity') or {}).get('phase') == 'Esperando intervención')


class AttentionInbox:
    def __init__(self, saved=None):
        source = saved.get('sessions', {}) if isinstance(saved, dict) else {}
        self.records = {}
        if isinstance(source, dict):
            for ident, record in source.items():
                if (isinstance(ident, str) and re.fullmatch(r'[\w:.-]{1,128}', ident)
                        and isinstance(record, dict)):
                    self.records[ident] = {key: timestamp(record.get(key)) for key in FIELDS}
        self.input_since = {}
        self._trim()

    def _trim(self):
        if len(self.records) > LIMIT:
            newest = sorted(self.records, key=lambda ident: max(self.records[ident].values()), reverse=True)[:LIMIT]
            self.records = {ident: self.records[ident] for ident in newest}

    def snapshot(self):
        # IDs, event times and acknowledgment watermarks only. Never prose.
        return {'version': 1, 'sessions': {ident: dict(record) for ident, record in self.records.items()}}

    def observe(self, chats, now):
        changed = False
        present = set()
        for chat in chats:
            ident = chat['id']
            present.add(ident)
            if chat.get('unavailable') or chat.get('state') == 'unknown':
                continue
            activity = chat.get('activity') or {}
            if needs_input(chat):
                self.input_since.setdefault(ident, now)
            else:
                self.input_since.pop(ident, None)
            error_at = max((timestamp(action.get('at')) for action in activity.get('actions', [])
                            if action.get('outcome') == 'error'), default=0)
            interrupted_at = timestamp(activity.get('finished_at')) if activity.get('phase') == 'Turno interrumpido' else 0
            fresh = ident not in self.records
            record = self.records.setdefault(ident, dict.fromkeys(FIELDS, 0.0))
            for kind, stamp in (('error', error_at), ('interrupted', interrupted_at)):
                if stamp > record[kind + '_at'] and stamp <= now + 5:
                    record[kind + '_at'] = stamp
                    # First discovery establishes a baseline, not a replay of
                    # every historical failure. Saved unseen events survive it.
                    if fresh:
                        record[kind + '_seen'] = stamp
                    changed = True
            changed = changed or fresh
        for ident in self.input_since.keys() - present:
            del self.input_since[ident]
        self._trim()
        return changed

    def acknowledge(self, ident, kind, at):
        record = self.records.get(ident)
        if not record or kind not in ('error', 'interrupted'):
            return False
        # A stale selection cannot acknowledge a newer event.
        if record[kind + '_at'] != at or record[kind + '_seen'] >= at:
            return False
        record[kind + '_seen'] = at
        return True

    def count(self, entries, notices):
        """Count without formatting titles or constructing UI rows in the tick."""
        return (sum(ident in entries for ident in self.input_since)
                + sum(record[kind + '_at'] > record[kind + '_seen']
                      for record in self.records.values() for kind in ('error', 'interrupted'))
                + sum(timestamp((notices.get(ident) or {}).get('completed_at'))
                      > timestamp((notices.get(ident) or {}).get('acknowledged_at')) for ident in entries))

    def rows(self, entries, notices, now, available=True):
        rows = []

        def add(ident, kind, at):
            entry = entries.get(ident) or {}
            chat = entry.get('chat') or {}
            stale = not available or entry.get('unavailable') or not chat or chat.get('state') == 'unknown'
            provider = 'Claude' if chat.get('provider') == 'claude' or ident.startswith('claude:') else 'Codex'
            rows.append({'key': f'{kind}:{ident}:{at}', 'id': ident, 'kind': kind, 'at': at,
                         'session': provider + ' · ' + safe_preview(chat.get('title') or ident[-8:], 70),
                         'reason': REASONS[kind] + (' · sin actualizar' if stale else ''),
                         'age': time_text(max(0, now - at)), 'available': bool(entry) and not stale,
                         'stale': bool(stale)})

        for ident, at in self.input_since.items():
            if ident in entries:
                add(ident, 'input', at)
        for ident, record in self.records.items():
            for kind in ('error', 'interrupted'):
                if record[kind + '_at'] > record[kind + '_seen']:
                    add(ident, kind, record[kind + '_at'])
        for ident in entries:
            record = notices.get(ident) or {}
            if timestamp(record.get('completed_at')) > timestamp(record.get('acknowledged_at')):
                add(ident, 'result', record['completed_at'])
        return sorted(rows, key=lambda row: (ORDER[row['kind']], row['at'], row['id']))
