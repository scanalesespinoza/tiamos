"""Dependency-light Claude CLI session validation and bounded transcript reading.

Shared by the desktop app and the root-owned elevated observer, so it must only import
the standard library and session_activity.
"""
from collections import deque
import datetime as dt
import json
import os
from pathlib import Path
import uuid

from session_activity import Activity, category, safe_preview, text_content


FILETIME_EPOCH = 116444736000000000


def linux_start_ticks(pid):
    """Process start time in clock ticks since boot (field 22 of /proc/<pid>/stat)."""
    try:
        stat = Path(f'/proc/{int(pid)}/stat').read_text()
        # The command name may contain spaces or parentheses; fields resume after the last ')'.
        return int(stat[stat.rindex(')') + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def started_with(record, client):
    """procStart is a Windows FILETIME on Windows and boot-relative clock ticks on Linux."""
    proc_start = int(record['procStart'])
    if proc_start >= FILETIME_EPOCH:
        born = (proc_start - FILETIME_EPOCH) / 10000000
        return abs(born - client['created_at']) < .1
    return os.name == 'posix' and proc_start == linux_start_ticks(client['pid'])


def valid_session(record, client):
    try:
        uuid.UUID(record['sessionId'])
        return (record['pid'] == client['pid'] and record.get('kind') == 'interactive'
            and record.get('entrypoint') == 'cli' and started_with(record, client))
    except (KeyError, TypeError, ValueError):
        return False


def tool_category(name, inputs):
    if name in {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}:
        return 'Edición de archivos'
    if name in {'Read', 'Glob', 'Grep'}:
        return 'Exploración de archivos'
    if name in {'WebFetch', 'WebSearch'}:
        return 'Investigación'
    if name in {'AskUserQuestion', 'ExitPlanMode'}:
        return 'Esperando intervención'
    return category(inputs.get('command', ''), name)


class ClaudeTrace:
    def __init__(self, path, session_id):
        self.path, self.session_id = Path(path), session_id
        self.offset = 0
        self.discarding = False
        self.activity = Activity()
        self.active = False
        self.failed = False
        self.last_text = ''
        self.title = ''
        self.custom_title = False
        self.tools = {}
        self.seen = deque(maxlen=512)

    def event(self, kind, stamp, **payload):
        self.activity.observe({'type': 'event_msg', 'payload': {'type': kind, **payload}}, stamp)

    def finish(self, stamp, failed=False):
        if not self.active:
            return
        self.activity.final = self.last_text
        self.event('task_aborted' if failed or self.failed else 'task_complete', stamp)
        self.active = False

    def observe(self, record):
        if record.get('isSidechain') or record.get('sessionId', record.get('session_id')) != self.session_id:
            return
        if record.get('type') == 'custom-title':
            self.title = safe_preview(record.get('customTitle') or '', 120)
            self.custom_title = bool(self.title)
            return
        if record.get('type') == 'ai-title':
            if not self.custom_title:
                self.title = safe_preview(record.get('aiTitle') or '', 120)
            return
        ident = record.get('uuid')
        if ident and ident in self.seen:
            return
        try:
            stamp = dt.datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00')).astimezone()
        except (KeyError, AttributeError, TypeError, ValueError):
            return
        if ident:
            self.seen.append(ident)
        kind = record.get('type')
        message = record.get('message') or {}
        content = message.get('content', []) if isinstance(message, dict) else []
        blocks = content if isinstance(content, list) else []
        if kind == 'user':
            results = [block for block in blocks if isinstance(block, dict) and block.get('type') == 'tool_result']
            for block in results:
                tool = block.get('tool_use_id')
                label = self.tools.pop(tool, 'Uso de herramientas')
                self.activity.add_action(label, stamp, 'error' if block.get('is_error') else 'ok', ident=tool)
                self.activity.phase = 'Revisando resultados'
            if results or record.get('isMeta'):
                return
            text = text_content(content)
            if text.startswith('[Request interrupted by user'):
                self.finish(stamp, failed=True)
                return
            if text:
                self.event('task_started', stamp, turn_id=ident)
                self.event('user_message', stamp, message=text)
                self.active, self.failed, self.last_text = True, False, ''
                self.tools.clear()
        elif kind == 'assistant':
            if record.get('isApiErrorMessage'):
                self.failed = True
                self.activity.add_action('Error de Claude', stamp, 'error', ident=ident)
            text = safe_preview(text_content(content))
            if text:
                self.last_text = self.activity.progress = text
                self.activity.updated_at = stamp.timestamp()
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get('type') == 'tool_use':
                    label = tool_category(block.get('name', ''), block.get('input') or {})
                    if len(self.tools) >= 256:
                        self.tools.pop(next(iter(self.tools)))
                    self.tools[block.get('id')] = label
                    self.activity.phase = label
                    self.activity.updated_at = stamp.timestamp()
                elif block.get('type') == 'thinking':
                    self.activity.phase = 'Analizando'
            if message.get('stop_reason') in {'end_turn', 'stop_sequence'}:
                self.finish(stamp)
        elif kind == 'system' and record.get('subtype') == 'turn_duration':
            self.finish(stamp)

    def read(self):
        if not self.path.exists():
            return
        if self.path.stat().st_size < self.offset:
            self.__init__(self.path, self.session_id)
        # Skip oversized API/context records; never retain their content between polls.
        limit, budget = 2 * 1024 * 1024, 4 * 1024 * 1024
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            consumed = 0
            while consumed < budget:
                start = stream.tell()
                line = stream.readline(limit + 1)
                if not line:
                    break
                consumed += len(line)
                complete = line.endswith(b'\n')
                if self.discarding or len(line) > limit:
                    self.discarding = not complete
                    self.offset = stream.tell()
                    continue
                if not complete:
                    self.offset = start
                    break
                self.offset = stream.tell()
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(record, dict):
                    self.observe(record)
