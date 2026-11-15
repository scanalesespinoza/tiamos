"""Measure an isolated real desktop monitor; never reads operator sessions.

Run on the same desktop before/after a change with matching arguments. Results
are observations, not machine-independent thresholds or CI pass/fail gates.
"""
import argparse
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from platform_runtime import background_options


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=int, default=6, choices=range(1, 129), metavar='1..128')
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--hidden', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error('--seconds must be between 1 and 60')
    with tempfile.TemporaryDirectory(prefix='tiamos-benchmark-') as folder:
        root = Path(folder)
        codex, state = root / 'codex', root / 'state'
        codex.mkdir(); state.mkdir()
        now = dt.datetime.now(dt.timezone.utc)
        identities = [f'11111111-2222-4333-8444-{index:012d}' for index in range(args.sessions)]
        (state / 'preferences.json').write_text(json.dumps({'quiet': args.quiet}), encoding='utf-8')
        (state / 'visibility.json').write_text(json.dumps({'hidden': identities if args.hidden else []}), encoding='utf-8')
        with closing(sqlite3.connect(codex / 'state_5.sqlite')) as db:
            db.execute('CREATE TABLE threads (id,title,cwd,rollout_path,source,archived,updated_at,attached_thread_parent_id)')
            for index, ident in enumerate(identities):
                trace = codex / f'{index}.jsonl'
                trace.write_text(json.dumps({'timestamp': now.isoformat(), 'type': 'event_msg',
                    'payload': {'type': 'task_started', 'turn_id': 'synthetic'}}) + '\n', encoding='utf-8')
                db.execute('INSERT INTO threads VALUES (?,?,?,?,?,0,?,NULL)',
                           (ident, f'Synthetic {index}', str(root), str(trace), 'cli', now.timestamp()))
            db.commit()
        env = dict(os.environ, TIAMOS_STATE_DIR=str(state), CODEX_HOME=str(codex),
                   CLAUDE_CONFIG_DIR=str(root / 'claude'), TIAMOS_DISABLE_DISCOVERY='1')
        with (root / 'monitor.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen([sys.executable, str(ROOT / 'tiamos.py'), 'serve'],
                                     cwd=ROOT, env=env, stdout=log, stderr=log, **background_options())
            try:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        status = json.loads((state / 'status.json').read_text(encoding='utf-8'))
                    except (OSError, ValueError):
                        status = {}
                    if status.get('chats') == args.sessions and not status.get('error'):
                        break
                    if child.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Synthetic monitor did not become ready')
                    time.sleep(.1)
                process = psutil.Process(child.pid)
                time.sleep(2)  # Exclude initial sprite generation and window creation.
                started = process.cpu_times()
                begin = time.monotonic()
                rss = []
                while time.monotonic() - begin < args.seconds:
                    rss.append(process.memory_info().rss)
                    time.sleep(.1)
                elapsed = time.monotonic() - begin
                ended = process.cpu_times()
                cpu = 100 * (ended.user + ended.system - started.user - started.system) / elapsed
                print(json.dumps({'sessions': args.sessions, 'quiet': args.quiet, 'hidden': args.hidden,
                                  'seconds': round(elapsed, 2), 'cpu_one_core_pct': round(cpu, 2),
                                  'rss_mib_max': round(max(rss) / 2**20, 2)}), flush=True)
            finally:
                (state / 'stop').touch()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=5)


if __name__ == '__main__':
    main()
