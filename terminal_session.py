"""Visible terminal owner; holds a per-session lock until Codex exits."""
import argparse
import ctypes
import json
import msvcrt
import os
import signal
import subprocess
import sys
import time
from cli_sessions import STATE, cli_executable, save, session_id, thread_info
from window_focus import Windows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args()
    ident = session_id(args.session)
    info = thread_info(ident)
    folder = STATE / 'cli-sessions'
    folder.mkdir(parents=True, exist_ok=True)
    lock = (folder / f'{ident}.lock').open('a+b')
    lock.seek(0); lock.write(b'1'); lock.flush(); lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print('Esta sesion ya tiene una terminal de Codex Float.')
        return
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    ctypes.windll.kernel32.SetConsoleTitleW(f'Codex CLI [{args.token}]')
    native = Windows()
    path = folder / f'{ident}.json'
    record = {'id': ident, 'token': args.token, 'pid': os.getpid(), 'started_at': time.time(),
              'heartbeat': time.time(), 'running': True, 'hwnd': None, 'cwd': info['cwd']}
    save(path, record)
    (STATE / 'cli-launches' / f'{ident}.json').unlink(missing_ok=True)
    process = None
    try:
        # The CLI owns Ctrl+C behavior; its watcher must survive turn interrupts.
        signal.signal(signal.SIGINT, lambda *_: None)
        process = subprocess.Popen([cli_executable(), 'resume', ident, '-C', info['cwd']])
        while process.poll() is None:
            if not record['hwnd']:
                candidates = native.terminal_windows(args.token)
                if len(candidates) == 1:
                    host = candidates[0]
                    record.update(hwnd=host.hwnd, window_pid=host.pid, executable=host.executable)
            record['heartbeat'] = time.time()
            save(path, record)
            time.sleep(1)
        record['exit_code'] = process.returncode
    except KeyboardInterrupt:
        # Codex receives the same console signal; give it time to close normally.
        if process:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
    finally:
        record.update(running=False, heartbeat=time.time())
        save(path, record)
        lock.close()
    if record.get('exit_code', 0):
        print('Codex termino con error. Puedes reabrirlo desde su avatar.')
        input('Enter para cerrar esta terminal...')


if __name__ == '__main__':
    main()
