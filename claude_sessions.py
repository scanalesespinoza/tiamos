"""Read validated local Claude CLI metadata and bounded transcript summaries."""
from collections import deque
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from cli_sessions import STATE, read, save
from session_activity import Activity, category, safe_preview, text_content


def valid_session(record, client):
    try:
        uuid.UUID(record['sessionId'])
        born = (int(record['procStart']) - 116444736000000000) / 10000000
        return (record['pid'] == client['pid'] and record.get('kind') == 'interactive'
            and record.get('entrypoint') == 'cli' and abs(born - client['created_at']) < .1)
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


class ClaudeSessions:
    def __init__(self, state=STATE):
        self.state = Path(state)
        self.known = read(self.state / 'claude-sessions.json', {})
        self.live = {}
        self.traces = {}

    def trace_for(self, info):
        ident, raw_id = info['id'], info['session_id']
        trace = self.traces.get(ident)
        if trace is None or not trace.path.exists():
            paths = list((Path(info['config_dir']) / 'projects').glob(f'*/{raw_id}.jsonl'))
            path = paths[0] if len(paths) == 1 else Path(info['config_dir']) / 'unavailable' / f'{raw_id}.jsonl'
            if trace is None or trace.path != path:
                trace = self.traces[ident] = ClaudeTrace(path, raw_id)
        return trace

    def metadata(self, clients, now, included=None):
        included = included or {}
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        self.known = {key: value for key, value in self.known.items() if value.get('last_seen', 0) >= midnight or key in included}
        for key, record in included.items():
            if record.get('provider') == 'claude':
                self.known.setdefault(key, dict(record))
        self.live = {}
        for client in clients:
            if client.get('provider') != 'claude':
                continue
            root = Path(client.get('config_dir') or Path.home() / '.claude')
            record = read(root / 'sessions' / f'{client["pid"]}.json', {})
            if not valid_session(record, client):
                continue
            raw_id = str(uuid.UUID(record['sessionId']))
            ident = 'claude:' + raw_id
            old = self.known.get(ident, {})
            self.known[ident] = {'id': ident, 'session_id': raw_id, 'cwd': record.get('cwd') or client['cwd'],
                'config_dir': str(root), 'provider': 'claude', 'cli_pid': client['pid'],
                'created_at': client['created_at'], 'last_seen': now.timestamp(),
                'first_seen': old.get('first_seen', now.timestamp())}
            self.live[ident] = record
        save(self.state / 'claude-sessions.json', self.known)
        metadata = []
        for key, value in self.known.items():
            trace = self.trace_for(value)
            trace.read()
            metadata.append(dict(value, name=trace.title or safe_preview(self.live.get(key, {}).get('name') or Path(value['cwd']).name, 60),
                title='', recent=value.get('last_seen', 0) >= midnight))
        return metadata

    def snapshot(self, terminals):
        result = []
        for ident, info in self.known.items():
            raw_id = info['session_id']
            trace = self.trace_for(info)
            record = self.live.get(ident)
            activity = trace.activity.summary()
            state = 'sleeping'
            if record:
                observed = record.get('status')
                if observed in {'working', 'running', 'busy', 'thinking'}:
                    state = 'working'
                elif observed in {'waiting', 'needs_input', 'waiting_for_permission', 'waiting_for_input'}:
                    state, activity['phase'] = 'working', 'Esperando intervención'
                elif observed != 'idle':
                    state = 'working' if trace.active else 'unknown'
                if state == 'sleeping' and trace.active:
                    activity['phase'] = 'En espera'
                    activity['finished_at'] = (record.get('statusUpdatedAt') or record.get('updatedAt') or 0) / 1000 or None
                elif state == 'working' and not trace.active:
                    activity['phase'] = 'Analizando' if not activity['phase'].startswith('Esperando') else activity['phase']
                    activity['started_at'] = (record.get('statusUpdatedAt') or 0) / 1000 or None
                    activity['finished_at'] = None
            terminal = dict(terminals.get(ident) or {'kind': 'unbound', 'started_at': info['first_seen']})
            terminal.update(live=bool(record), running=bool(record))
            title = trace.title or safe_preview((record or {}).get('name') or Path(info['cwd']).name or 'Claude CLI', 60)
            result.append({'id': ident, 'provider': 'claude', 'session_id': raw_id, 'cwd': info['cwd'],
                'title': title, 'project': safe_preview(Path(info['cwd']).name, 60), 'state': state,
                'terminal': terminal, 'activity': activity})
        self.traces = {key: value for key, value in self.traces.items() if key in self.known}
        return result


def claude_executable():
    if os.name != 'nt':
        executable = shutil.which('claude')
        if executable:
            return executable
        raise RuntimeError('Instala Claude CLI y agrega claude al PATH.')
    # Prefer the explicitly configured npm installation over a retained native copy.
    candidates = [Path.home() / '.npm-global/node_modules/@anthropic-ai/claude-code/bin/claude.exe',
        Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe',
        Path.home() / '.local/bin/claude.exe']
    for path in candidates:
        if path.is_file():
            return str(path)
    raise RuntimeError('No se encuentra el ejecutable de Claude CLI.')


def launch_claude(chat):
    if (chat.get('terminal') or {}).get('live'):
        raise RuntimeError('Claude sigue abierto. Vincula su ventana desde el menú del avatar.')
    raw_id = str(uuid.UUID(chat['session_id']))
    from terminal_discovery import native_clients
    for client in native_clients():
        if client.get('provider') != 'claude':
            continue
        if os.name != 'nt' and Path(client['cwd']).resolve() == Path(chat['cwd']).resolve():
            raise RuntimeError('Claude ya está abierto en esta carpeta. Selecciona su pestaña antes de reanudar otra sesión.')
        root = Path(client.get('config_dir') or Path.home() / '.claude')
        record = read(root / 'sessions' / f'{client["pid"]}.json', {})
        if record.get('sessionId') == raw_id and valid_session(record, client):
            raise RuntimeError('Esta sesión de Claude ya tiene un cliente activo.')
    cwd = str(Path(chat['cwd']).resolve())
    if not Path(cwd).is_dir():
        raise RuntimeError('La carpeta de esta sesión de Claude ya no existe.')
    pending_path = STATE / 'claude-launches' / f'{raw_id}.json'
    if time.time() - read(pending_path, {}).get('requested_at', 0) < 20:
        return
    executable = claude_executable()
    terminal = shutil.which('wt.exe')
    command = [executable, '--resume', raw_id]
    save(pending_path, {'requested_at': time.time()})
    try:
        if os.name != 'nt':
            from platform_runtime import launch_terminal
            launch_terminal(command, cwd)
        elif terminal and not any(';' in value for value in (cwd, executable)):
            subprocess.Popen([terminal, '-w', 'new', 'new-tab', '-d', cwd, *command], cwd=cwd)
        else:
            subprocess.Popen(command, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    except OSError:
        pending_path.unlink(missing_ok=True)
        raise
