"""Read validated local Claude CLI metadata and bounded transcript summaries."""
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from cli_sessions import STATE, read, save
from session_activity import safe_preview
from claude_trace import ClaudeTrace, tool_category, valid_session  # noqa: F401 (re-exported)


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
        if os.name != 'nt':
            raise RuntimeError('Claude sigue abierto. Selecciona su pestaña en tu terminal.')
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
