"""Opt-in, metadata-only observation of elevated CLI children of a desktop user.

The privileged service runs a root-owned copy of this standalone module. It
reads process identities and ancestry only: no transcripts, environment,
arguments, credentials, model calls, terminal contents or launch commands.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile
import time

import psutil

TERMINALS = {'kitty', 'gnome-terminal-server', 'gnome-terminal-', 'konsole',
             'xterm', 'ptyxis', 'kgx', 'alacritty', 'ghostty', 'xfce4-terminal'}
MAX_SESSIONS = 64
MAX_BYTES = 65536
MAX_AGE = 8


def feed_path(uid):
    return Path('/run') / f'agentlings-observer-{uid}' / 'sessions.json'


def describe(process, desktop_uid):
    """A root CLI belongs here only through a live, user-owned terminal ancestor."""
    try:
        provider = process.name().lower()
        if provider not in ('codex', 'claude') or process.uids().real != 0 or not process.terminal():
            return None
        terminal = next((parent for parent in process.parents()[:32]
                         if parent.uids().real == desktop_uid and parent.name().lower() in TERMINALS), None)
        if terminal is None:
            return None
        return {'pid': process.pid, 'created_at': process.create_time(), 'provider': provider,
                'terminal_pid': terminal.pid, 'terminal_created_at': terminal.create_time()}
    except (psutil.Error, OSError):
        return None


def collect(uid, processes=None, now=None):
    processes = psutil.process_iter(['name']) if processes is None else processes
    sessions = []
    for process in processes:
        try:
            if process.name().lower() not in ('codex', 'claude'):
                continue
            record = describe(process, uid)
            if record:
                sessions.append(record)
        except psutil.Error:
            continue
        if len(sessions) >= MAX_SESSIONS:
            break
    return {'version': 1, 'uid': uid, 'heartbeat': time.time() if now is None else now,
            'sessions': sorted(sessions, key=lambda row: (row['created_at'], row['pid']))}


def write_feed(path, data, gid):
    parent = path.parent
    parent.mkdir(mode=0o750, parents=False, exist_ok=True)
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError('Observer directory must be root-owned and not writable by other users.')
    os.chown(parent, 0, gid)
    os.chmod(parent, 0o750)
    fd, name = tempfile.mkstemp(prefix='.snapshot-', dir=parent)
    try:
        os.fchown(fd, 0, gid)
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def load_feed(path, uid, now=None, trusted_uid=0):
    """Reject stale, symlinked, oversized or user-writable observations."""
    now = time.time() if now is None else now
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != trusted_uid or parent.st_mode & 0o022:
        raise ValueError('Untrusted observer directory')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != trusted_uid or info.st_mode & 0o022 or info.st_size > MAX_BYTES:
            raise ValueError('Untrusted observer snapshot')
        data = json.loads(stream.read(MAX_BYTES + 1))
    if not isinstance(data, dict) or data.get('version') != 1 or data.get('uid') != uid:
        raise ValueError('Unexpected observer protocol or desktop owner')
    heartbeat = data.get('heartbeat')
    if not isinstance(heartbeat, (int, float)) or not 0 <= now-heartbeat <= MAX_AGE:
        raise ValueError('Stale observer snapshot')
    rows = data.get('sessions')
    if not isinstance(rows, list) or len(rows) > MAX_SESSIONS:
        raise ValueError('Invalid observer session list')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or row.get('provider') not in ('codex', 'claude'):
            raise ValueError('Invalid observer provider')
        if any(type(row.get(key)) is not int or row[key] <= 0 for key in ('pid', 'terminal_pid')):
            raise ValueError('Invalid process identity')
        if any(not isinstance(row.get(key), (int, float)) or not 0 < row[key] <= now
               for key in ('created_at', 'terminal_created_at')):
            raise ValueError('Invalid process birth')
        ident = f"elevated:{row['provider']}:{row['pid']}:{int(row['created_at']*1000)}"
        if ident in seen:
            raise ValueError('Duplicate process identity')
        seen.add(ident)
        # Keep IDs stable across polls, including when process numbers are reused.
        result.append({'id': ident, 'provider': row['provider'], 'state': 'unknown',
            'title': f"Admin {len(result)+1}",
            'project': 'Sesión elevada', 'activity': {},
            'terminal': {'kind': 'unbound', 'live': True, 'elevated': True,
                         'cli_pid': row['pid'], 'created_at': row['created_at'],
                         'terminal_pid': row['terminal_pid'], 'terminal_created_at': row['terminal_created_at']}})
    return result


class ElevatedSessions:
    def __init__(self):
        self.uid = os.getuid()
        self.status = {'enabled': False, 'sessions': 0, 'error': None}

    def snapshot(self):
        try:
            rows = load_feed(feed_path(self.uid), self.uid)
            self.status = {'enabled': True, 'sessions': len(rows), 'error': None}
            return rows
        except FileNotFoundError:
            self.status = {'enabled': False, 'sessions': 0, 'error': None}
        except (OSError, ValueError, TypeError):
            self.status = {'enabled': True, 'sessions': 0, 'error': 'Observador elevado sin datos válidos recientes.'}
        return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True, type=int)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0 or args.uid <= 0:
        parser.error('A root service and a non-root desktop UID are required.')
    import pwd
    account = pwd.getpwuid(args.uid)
    while True:
        write_feed(feed_path(args.uid), collect(args.uid), account.pw_gid)
        if args.once:
            return
        time.sleep(2)


if __name__ == '__main__':
    main()
