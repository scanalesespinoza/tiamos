"""Read-only POSIX session discovery without terminal UI automation."""
import os
from pathlib import Path
import time
import uuid

import psutil
from cli_sessions import STATE, read, save
from claude_sessions import ClaudeSessions
from session_history import load_history, history_pin


def native_clients():
    result = []
    for process in psutil.process_iter(['pid', 'name']):
        try:
            name = (process.info['name'] or '').lower()
            if name not in {'codex', 'claude', 'node', 'nodejs'}:
                continue
            if process.uids().real != os.getuid() or not process.terminal():
                continue
            provider = name if name in {'codex', 'claude'} else None
            if provider is None:
                # Inspect only the node entry script, never retain prompts/arguments.
                argv = process.cmdline()
                script = argv[1].replace('\\', '/') if len(argv) > 1 else ''
                if script.endswith('/@anthropic-ai/claude-code/cli.js'):
                    provider = 'claude'
                elif script.endswith('/@openai/codex/bin/codex.js'):
                    # npm's Codex wrapper launches a native client; count that child once.
                    continue
                else:
                    continue
            ident, config_dir = None, None
            try:
                for file in process.open_files():
                    path = Path(file.path)
                    if path.suffix != '.jsonl' or 'subagents' in path.parts:
                        continue
                    try:
                        candidate = str(uuid.UUID(path.stem[-36:]))
                    except ValueError:
                        continue
                    if provider == 'claude' and path.parent.parent.name == 'projects':
                        ident, config_dir = candidate, str(path.parent.parent.parent)
                        break
                    if provider == 'codex' and path.name.startswith('rollout-'):
                        ident = candidate
                        break
            except psutil.Error:
                pass
            result.append({'pid': process.pid, 'cwd': process.cwd(), 'provider': provider,
                           'created_at': process.create_time(), 'session_id': ident,
                           'config_dir': config_dir, 'terminal_id': process.terminal(),
                           'terminal_pid': terminal_ancestor(process)})
        except (psutil.Error, OSError):
            continue
    return result


def terminal_ancestor(process):
    try:
        for ancestor in process.parents()[:32]:
            if ancestor.name() in {'gnome-terminal-server', 'gnome-terminal-', 'konsole', 'xterm', 'kitty', 'ptyxis', 'kgx', 'xfce4-terminal'}:
                return ancestor.pid
    except psutil.Error:
        pass
    return None


def match_client(thread, clients, threads):
    provider = thread.get('provider', 'codex')
    raw_id = thread['id'].removeprefix('claude:')
    exact = [client for client in clients if client['provider'] == provider and client.get('session_id') == raw_id]
    if len(exact) == 1:
        return exact[0]
    peers = [row for row in threads if row.get('provider', 'codex') == provider and row.get('recent', True)
             and row['cwd'] == thread['cwd']]
    owners = [client for client in clients if client['provider'] == provider and client['cwd'] == thread['cwd']]
    if len(peers) == len(owners) == 1 and not owners[0].get('session_id'):
        return owners[0]
    return None


class PortableDiscovery:
    def __init__(self, state=STATE):
        self.state = Path(state)

    def close(self): pass

    def update(self, threads, clients=None):
        from terminal_discovery import keep_daily_sessions
        clients = native_clients() if clients is None else clients
        current = {}
        from window_focus import Windows
        from linux_tabs import match_terminal
        windows = Windows().all_terminal_windows()
        for thread in threads:
            if not thread.get('recent', True):
                continue
            client = match_client(thread, clients, threads)
            if client:
                current[thread['id']] = {'id': thread['id'], 'kind': 'unbound', 'live': True,
                    'running': True, 'selected': False, 'cli_pid': client['pid'], 'created_at': client['created_at'],
                    'started_at': time.time(), 'heartbeat': time.time()}
                unique = bool(client.get('terminal_pid')) and sum(c.get('terminal_pid') == client['terminal_pid'] for c in clients) == 1
                current[thread['id']].update(match_terminal(thread, dict(client, terminal_unique=unique), windows))
        previous = read(self.state / 'external-cli.json', {}).get('sessions', {})
        current = keep_daily_sessions(current, previous, {client['pid'] for client in clients})
        births = {client['pid']: client['created_at'] for client in clients}
        for record in current.values():
            if births.get(record.get('cli_pid')) != record.get('created_at'):
                record.update(live=False, running=False)
        save(self.state / 'external-cli.json', {'heartbeat': time.time(), 'sessions': current})
        return current


class PortableClaudeSessions(ClaudeSessions):
    def __init__(self, state=STATE):
        super().__init__(state)
        self.scanned_at = float('-inf')
        self.day = None

    def metadata(self, clients, now, included=None):
        included = included or {}
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        self.known = {key: value for key, value in self.known.items()
                      if value.get('last_seen', 0) >= midnight or key in included}
        if time.monotonic() - self.scanned_at >= 30 or self.day != now.date():
            roots = {client['config_dir'] for client in clients if client.get('config_dir')}
            records, _ = load_history(None, roots, since=midnight)
            self.known.update({record['id']: history_pin(record) for record in records})
            self.scanned_at, self.day = time.monotonic(), now.date()
        for key, record in included.items():
            if record.get('provider') == 'claude':
                self.known.setdefault(key, history_pin(record))
        metadata, self.live = [], {}
        candidates = list(self.known.values())
        for ident, info in self.known.items():
            trace = self.trace_for(info)
            trace.read()
            client = match_client(info, clients, candidates)
            if client:
                self.live[ident] = {'status': 'working' if trace.active else 'idle'}
            metadata.append(dict(info, name=trace.title, title='', recent=info.get('last_seen', 0) >= midnight))
        save(self.state / 'claude-sessions.json', self.known)
        return metadata
