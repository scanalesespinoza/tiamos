"""Incremental local lifecycle reader shared with the privileged observer."""
import datetime as dt
import json
from pathlib import Path
from session_activity import Activity


class Trace:
    """Incrementally inspect lifecycle and bounded, sanitized activity metadata."""
    END_EVENTS = {'task_complete', 'task_completed', 'turn_aborted', 'task_aborted', 'task_interrupted', 'turn_cancelled', 'session_end'}

    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0
        self.pending = b''
        self.active = set()
        self.last_activity = None
        self.activity = Activity()

    def read(self):
        if self.path.stat().st_size < self.offset:
            self.offset, self.pending = 0, b''
            self.active.clear()
            self.last_activity = None
            self.activity = Activity()
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            content = self.pending + stream.read()
            self.offset = stream.tell()
        lines = content.split(b'\n')
        self.pending = lines.pop()
        for line in lines:
            try:
                item = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(item, dict) or not isinstance(item.get('payload'), dict):
                continue
            payload = item.get('payload', {})
            kind = payload.get('type')
            try:
                stamp = dt.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')).astimezone()
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            self.activity.observe(item, stamp)
            if item.get('type') != 'event_msg' or kind not in {'task_started', 'user_message'} | self.END_EVENTS:
                continue
            if self.last_activity is None or stamp > self.last_activity:
                self.last_activity = stamp
            turn = payload.get('turn_id') or payload.get('task_id')
            if kind == 'task_started':
                self.active.add(turn or 'current')
            elif kind in self.END_EVENTS:
                if turn:
                    self.active.discard(turn)
                    self.active.discard('current')
                else:
                    self.active.clear()

