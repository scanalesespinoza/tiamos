#!/usr/bin/python3
"""Kitty-launched bridge: export identities and allow focus of existing panes only.

Launch using Kitty's supported remote_control_script action. Its private inherited
FD never leaves this process. The desktop socket accepts snapshot/focus only;
terminal text, commands and environment are neither exposed nor persisted.
"""
import json
import os
from pathlib import Path
import socket
import struct
import time


def endpoint():
    return Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))/'agentlings-kitty.sock'


def request(command, **params):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(.6)
        client.connect(str(endpoint()))
        client.sendall(json.dumps(dict(command=command, **params)).encode()+b'\n')
        data = b''
        while not data.endswith(b'\n') and len(data) < 65536:
            part = client.recv(65536)
            if not part: break
            data += part
    result = json.loads(data)
    if 'error' in result: raise RuntimeError(result['error'])
    return result


def filtered_windows(tree, pid):
    rows = []
    for oswindow in tree:
        for tab in oswindow.get('tabs', []):
            for pane in tab.get('windows', []):
                rows.append({'id': pane['id'], 'tab': tab['id'], 'os_window': oswindow['id'],
                    'pid': pane['pid'], 'terminal_pid': pid,
                    'selected': bool(tab.get('is_active') and pane.get('is_active'))})
    return rows


def main():
    address = os.environ.get('KITTY_LISTEN_ON', '')
    if not address.startswith('fd:'):
        raise SystemExit('Launch from Kitty with remote_control_script.')
    remote = socket.socket(fileno=int(address[3:]))
    remote.settimeout(2)
    import psutil
    parent = next((p for p in psutil.Process().parents() if p.name() == 'kitty'), None)
    if parent is None: raise SystemExit('No Kitty parent.')
    def call(cmd, payload):
        remote.sendall(b'\x1bP@kitty-cmd'+json.dumps({'cmd':cmd,'version':[0,47,1],
            'no_response':False,'payload':payload}).encode()+b'\x1b\\')
        data = b''
        while not data.endswith(b'\x1b\\') and len(data) < 4*1024*1024:
            part = remote.recv(65536)
            if not part: raise ConnectionError('Kitty closed')
            data += part
        answer = json.loads(data[len(b'\x1bP@kitty-cmd'):-2])
        if not answer.get('ok'): raise RuntimeError('Kitty rejected the request')
        return answer.get('data')
    path = endpoint()
    # Keep an existing healthy bridge, avoiding disconnects on config reload.
    if path.exists():
        try:
            request('snapshot')
            return
        except (OSError, ValueError, RuntimeError):
            path.unlink()
    os.umask(0o077)
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(path)); server.listen(4); server.settimeout(3)
        try:
            while parent.is_running():
                try: client, _ = server.accept()
                except socket.timeout: continue
                with client:
                    client.settimeout(1)
                    try:
                        _, uid, _ = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                        if uid != os.getuid(): continue
                        data = b''
                        while not data.endswith(b'\n') and len(data) < 1024:
                            part = client.recv(1024-len(data))
                            if not part: break
                            data += part
                        query = json.loads(data)
                        if not isinstance(query, dict): raise ValueError('Invalid request')
                        command = query.get('command')
                        if command not in ('snapshot','focus'): raise ValueError('Unsupported command')
                        rows = filtered_windows(json.loads(call('ls', {})), parent.pid)
                        if command == 'focus':
                            target = query.get('id')
                            if type(target) is not int or not any(r['id']==target for r in rows):
                                raise ValueError('Pane no longer exists')
                            call('focus-window', {'match':f'id:{target}'})
                        answer = {'windows': rows, 'heartbeat':time.time()}
                    except (OSError, ValueError, RuntimeError) as error:
                        answer = {'error':str(error)}
                    try: client.sendall(json.dumps(answer).encode()+b'\n')
                    except OSError: pass
        finally:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
