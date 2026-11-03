"""Discover existing CLI clients and bind their Windows Terminal tabs."""
import ctypes as C
from ctypes import wintypes as W
import json
from contextlib import closing
from collections import Counter
import datetime as dt
import ntpath
import os
from pathlib import Path
import queue
import sqlite3
import subprocess
import threading
import time

import psutil
from cli_sessions import BASE, STATE, CODEX, read, save
from window_focus import Windows


class _ProcessEntry(C.Structure):
    _fields_ = [('size', W.DWORD), ('usage', W.DWORD), ('pid', W.DWORD),
        ('heap', C.c_size_t), ('module', W.DWORD), ('threads', W.DWORD),
        ('parent', W.DWORD), ('priority', W.LONG), ('flags', W.DWORD),
        ('name', W.WCHAR * 260)]


class _LastInput(C.Structure):
    _fields_ = [('size', W.UINT), ('tick', W.DWORD)]


def normalize_cwd(value):
    if value == '~':
        value = str(Path.home())
    return ntpath.normcase(ntpath.normpath(value.removeprefix('\\\\?\\')))


def match_session(tab, threads, live_cwds):
    workspace = normalize_cwd(tab.get('workspace') or '')
    if workspace not in live_cwds:
        return None
    candidates = [thread for thread in threads if normalize_cwd(thread['cwd']) == workspace]
    title = tab.get('title') or ''
    named = [thread for thread in candidates if title in (thread.get('name'), thread.get('title'))]
    if len(named) == 1:
        return named[0]['id']
    recent_named = [thread for thread in named if thread.get('recent', True)]
    if len(recent_named) == 1:
        return recent_named[0]['id']
    # Renamed conversations can have a stale cached footer; only use a unique cwd.
    recent = [thread for thread in candidates if thread.get('recent', True)]
    if isinstance(live_cwds, dict) and live_cwds[workspace] != 1:
        return None
    return recent[0]['id'] if len(recent) == 1 else None


def keep_daily_sessions(current, previous, live_pids, now=None):
    now = now or dt.datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    result = dict(current)
    for ident, record in previous.items():
        if ident in result or record.get('started_at', 0) < midnight:
            continue
        owners = record.get('cli_pids', [record.get('cli_pid')])
        live = any(pid in live_pids for pid in owners)
        result[ident] = dict(record, live=live, running=live, selected=False, heartbeat=now.timestamp())
    return result


class TabBridge:
    def __init__(self):
        self.process = subprocess.Popen(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
            '-File', str(BASE / 'terminal_tabs.ps1')], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        self.responses = queue.Queue()
        self.ready = False

        def drain():
            for line in self.process.stdout:
                try:
                    self.responses.put(json.loads(line))
                except ValueError:
                    pass

        self.reader_thread = threading.Thread(target=drain, daemon=True)
        self.reader_thread.start()

    def call(self, request):
        self.process.stdin.write(json.dumps(request) + '\n')
        self.process.stdin.flush()
        try:
            # Cold PowerShell/.NET assembly loading can exceed a normal query.
            response = self.responses.get(timeout=5 if self.ready else 15)
            self.ready = True
            return response
        except queue.Empty:
            self.close()
            raise RuntimeError('Windows Terminal no respondio a la consulta de pestanas.')

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=2)
        self.reader_thread.join(timeout=1)
        self.process.stdout.close()


def select_tab(record):
    bridge = TabBridge()
    try:
        reply = bridge.call({'mode': 'select', 'windows': [record['hwnd']], 'tab_id': record['tab_id']})
        if not reply.get('tabs'):
            raise RuntimeError('La pestana original ya no esta disponible.')
    finally:
        bridge.close()


def native_clients():
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Process32FirstW.argtypes = [W.HANDLE, C.POINTER(_ProcessEntry)]
    kernel.Process32NextW.argtypes = [W.HANDLE, C.POINTER(_ProcessEntry)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == C.c_void_p(-1).value:
        raise OSError('No se pudo consultar los procesos de Windows.')
    catalog = {}
    try:
        entry = _ProcessEntry()
        entry.size = C.sizeof(entry)
        success = kernel.Process32FirstW(handle, C.byref(entry))
        while success:
            catalog[entry.pid] = {'name': entry.name.lower(), 'parent': entry.parent}
            success = kernel.Process32NextW(handle, C.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    result = []
    for pid, metadata in catalog.items():
        if metadata['name'] != 'codex.exe':
            continue
        parent = catalog.get(metadata['parent'], {}).get('name')
        if parent not in {'node.exe', 'powershell.exe', 'pwsh.exe', 'cmd.exe'}:
            continue
        try:
            process = psutil.Process(pid)
            command = process.cmdline()
            if 'app-server' in command or (len(command) > 1 and command[1] in {'exec', 'review', 'debug'}):
                continue
            # Read only the terminal-session key; never retain the environment.
            terminal_id = process.environ().get('WT_SESSION')
            if terminal_id:
                result.append({'pid': process.pid, 'cwd': process.cwd(), 'terminal_id': terminal_id})
        except (psutil.Error, OSError):
            continue
    return result


def idle_seconds():
    info = _LastInput()
    info.size = C.sizeof(info)
    if not C.windll.user32.GetLastInputInfo(C.byref(info)):
        return 0
    C.windll.kernel32.GetTickCount64.restype = C.c_ulonglong
    return ((C.windll.kernel32.GetTickCount64() - info.tick) & 0xffffffff) / 1000


def discovery_signature(handles, clients, threads):
    """Invalidate tab inspection when clients or conversation identities change."""
    return (
        tuple(sorted(handles)),
        tuple(sorted((client['pid'], client.get('terminal_id', ''), normalize_cwd(client['cwd'])) for client in clients)),
        tuple(sorted((thread['id'], thread.get('name') or '', thread.get('title') or '', normalize_cwd(thread['cwd'])) for thread in threads)),
    )


class TerminalDiscovery:
    def __init__(self):
        self.bridge = None
        self.native = Windows()
        self.cache = read(STATE / 'tab-bindings.json', {})
        self.last_scan_signature = None

    def close(self):
        if self.bridge:
            self.bridge.close()

    def publish(self, current, clients):
        previous = read(STATE / 'external-cli.json', {}).get('sessions', {})
        result = keep_daily_sessions(current, previous, {client['pid'] for client in clients})
        save(STATE / 'external-cli.json', {'heartbeat': time.time(), 'sessions': result})
        return result

    def update(self, threads):
        clients = native_clients()
        cwds = Counter(normalize_cwd(client['cwd']) for client in clients)
        windows = self.native.all_terminal_windows()
        handles = [window.hwnd for window in windows]
        signature = discovery_signature(handles, clients, threads)
        if not handles or not clients:
            return self.publish({}, clients)
        if self.bridge is None:
            self.bridge = TabBridge()
        inspect_all = signature != self.last_scan_signature and idle_seconds() >= 2
        try:
            reply = self.bridge.call({'mode': 'scan', 'windows': handles, 'inspect_all': inspect_all})
        except (OSError, RuntimeError):
            self.bridge = None
            raise
        if reply.get('error'):
            raise RuntimeError('No se pudieron inspeccionar las pestanas de Windows Terminal.')
        if inspect_all:
            self.last_scan_signature = signature
        by_id = {thread['id']: thread for thread in threads}
        result = {}
        for tab in reply['tabs']:
            key = f'{tab["hwnd"]}:{tab["tab_id"]}'
            ident = match_session(tab, threads, cwds)
            cached = self.cache.get(key)
            if ident is None and cached and (not tab['selected'] or tab.get('workspace')):
                owner_ids = cached.get('cli_pids', [cached.get('cli_pid')])
                owners = [client for client in clients if client['pid'] in owner_ids]
                if owners and cached['id'] in by_id and any(normalize_cwd(owner['cwd']) == normalize_cwd(by_id[cached['id']]['cwd']) for owner in owners):
                    ident = cached['id']
            if ident is None:
                continue
            owners = [client for client in clients if normalize_cwd(client['cwd']) == normalize_cwd(by_id[ident]['cwd'])]
            owner_pid = owners[0]['pid'] if len(owners) == 1 else None
            host = next(window for window in windows if window.hwnd == tab['hwnd'])
            result[ident] = {'id': ident, 'kind': 'tab', 'live': True, 'running': True,
                'heartbeat': time.time(), 'started_at': time.time(), 'hwnd': host.hwnd,
                'window_pid': host.pid, 'executable': host.executable, 'tab_id': tab['tab_id'],
                'selected': tab['selected'], 'cli_pid': owner_pid, 'cli_pids': [client['pid'] for client in owners]}
            self.cache[key] = {'id': ident, 'cli_pids': [client['pid'] for client in owners]}
        save(STATE / 'tab-bindings.json', self.cache)
        return self.publish(result, clients)


def refresh_external():
    midnight = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    with closing(sqlite3.connect((CODEX / 'state_5.sqlite').as_uri() + '?mode=ro', uri=True)) as connection:
        rows = connection.execute('''SELECT id,title,name,cwd,updated_at FROM threads
            WHERE archived=0 AND attached_thread_parent_id IS NULL ORDER BY updated_at DESC LIMIT 500''').fetchall()
    metadata = [{'id': r[0], 'title': r[1], 'name': r[2], 'cwd': r[3], 'recent': r[4] >= midnight} for r in rows]
    discovery = TerminalDiscovery()
    try:
        return discovery.update(metadata)
    finally:
        discovery.close()
