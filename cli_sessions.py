"""Launch and locate native Codex CLI sessions without the desktop app."""
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

BASE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'CodexFloat'
CODEX = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def read(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def session_id(value):
    return str(uuid.UUID(value))


def cli_executable():
    # Prefer the separately installed CLI, independent of the desktop package.
    npm = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / 'npm/node_modules/@openai/codex/node_modules'
    candidates = list(npm.glob('**/codex.exe')) if npm.exists() else []
    if candidates:
        return str(candidates[0])
    executable = shutil.which('codex.exe')
    if executable:
        return executable
    raise RuntimeError('Instala el CLI independiente: npm install -g @openai/codex')


class LocalServer:
    """Short-lived metadata connection; never submits a model turn."""
    def __enter__(self):
        self.process = subprocess.Popen([cli_executable(), 'app-server'], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.messages = queue.Queue()
        self.sequence = 0

        def drain():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    pass

        threading.Thread(target=drain, daemon=True).start()
        try:
            self.call('initialize', {'clientInfo': {'name': 'codex_float', 'version': '0.2.0'}})
            self.send({'method': 'initialized', 'params': {}})
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def call(self, method, params):
        self.sequence += 1
        self.send({'id': self.sequence, 'method': method, 'params': params})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                message = self.messages.get(timeout=max(.1, deadline - time.monotonic()))
            except queue.Empty:
                break
            if message.get('id') == self.sequence:
                if 'error' in message:
                    raise RuntimeError(message['error'].get('message', 'Error de Codex'))
                return message['result']
        raise RuntimeError(f'Codex no respondio a {method}')

    def __exit__(self, *_):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=3)


def create_session(cwd):
    directory = Path(cwd).resolve()
    if not directory.is_dir():
        raise RuntimeError(f'No existe la carpeta: {directory}')
    with LocalServer() as server:
        ident = server.call('thread/start', {'cwd': str(directory)})['thread']['id']
        # Naming also flushes the initially empty conversation to persistent history.
        server.call('thread/name/set', {'threadId': ident, 'name': f'Codex CLI - {directory.name}'})
    return ident


def registrations(state=STATE):
    result = {}
    directory = state / 'cli-sessions'
    if directory.exists():
        for path in directory.glob('*.json'):
            value = read(path)
            if isinstance(value, dict) and value.get('id') == path.stem:
                value['live'] = value.get('running', False) and time.time() - value.get('heartbeat', 0) < 10
                result[path.stem] = value
    return result


def thread_info(ident):
    ident = session_id(ident)
    with closing(sqlite3.connect((CODEX / 'state_5.sqlite').as_uri() + '?mode=ro', uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT id,COALESCE(NULLIF(name,''),title) AS title,cwd,source,rollout_path FROM threads WHERE id=? AND archived=0", (ident,)).fetchone()
    if not row:
        raise RuntimeError('No se encuentra esa sesion local de Codex.')
    result = dict(row)
    result['cwd'] = result['cwd'].removeprefix('\\\\?\\')
    return result


def launch(ident):
    from window_focus import Windows
    ident = session_id(ident)
    info = thread_info(ident)
    existing = registrations().get(ident)
    native = Windows()
    if existing and existing['live']:
        window = native.inspect(existing.get('hwnd'))
        if window and window.pid == existing.get('window_pid') and existing.get('token') in window.title:
            native.activate(window)
        # A live wrapper may still be starting; never launch a second one.
        return ident
    pending_path = STATE / 'cli-launches' / f'{ident}.json'
    pending = read(pending_path, {})
    if time.time() - pending.get('requested_at', 0) < 20:
        return ident
    # Do not attach a second client to an unmanaged active task.
    from codex_float import Trace
    trace = Trace(info['rollout_path'])
    try:
        trace.read()
    except FileNotFoundError:
        pass
    if trace.active and not existing:
        raise RuntimeError('La sesion tiene un turno activo. Espera su fin o vincula su terminal existente.')
    if not Path(info['cwd']).is_dir():
        raise RuntimeError(f'La carpeta de la sesion ya no existe: {info["cwd"]}')
    token = uuid.uuid4().hex[:12]
    save(pending_path, {'requested_at': time.time(), 'token': token})
    python = str(Path(sys.executable).with_name('python.exe'))
    command = [python, str(BASE / 'terminal_session.py'), '--session', ident, '--token', token]
    terminal = shutil.which('wt.exe')
    try:
        if terminal and not any(';' in value for value in (info['cwd'], str(BASE), python)):
            # Fixed session-specific title + a dedicated window removes tab ambiguity.
            subprocess.Popen([terminal, '-w', 'new', 'new-tab', '--title', f'Codex CLI [{token}]',
                '--suppressApplicationTitle', '-d', info['cwd'], *command], cwd=info['cwd'])
        else:
            subprocess.Popen(command, cwd=info['cwd'], creationflags=subprocess.CREATE_NEW_CONSOLE)
    except OSError:
        pending_path.unlink(missing_ok=True)
        raise
    return ident
