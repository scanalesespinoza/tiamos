"""Exercise an actual packaged desktop process with synthetic local session data."""
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time


def main():
    executable = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix='codex-float-smoke-') as folder:
        root = Path(folder)
        codex = root / 'codex'; codex.mkdir()
        state = root / 'state'
        now = dt.datetime.now(dt.timezone.utc)
        ident = '11111111-2222-4333-8444-555555555555'
        trace = codex / 'session.jsonl'
        records = [{'timestamp': now.isoformat(), 'type': 'event_msg', 'payload': {'type': event, 'turn_id': 'test'}}
                   for event in ('task_started', 'task_complete')]
        trace.write_text('\n'.join(json.dumps(record) for record in records) + '\n', encoding='utf-8')
        with sqlite3.connect(codex / 'state_5.sqlite') as db:
            db.execute('CREATE TABLE threads (id,title,cwd,rollout_path,source,archived,updated_at,attached_thread_parent_id)')
            db.execute('INSERT INTO threads VALUES (?,?,?,?,?,0,?,NULL)',
                       (ident, 'Release smoke session', str(root), str(trace), 'cli', now.timestamp()))
        env = dict(os.environ, CODEX_FLOAT_STATE_DIR=str(state), CODEX_HOME=str(codex), CLAUDE_CONFIG_DIR=str(root / 'claude'))
        def run(*args):
            return subprocess.run([executable, *args], env=env, capture_output=True, text=True, timeout=35, check=True)
        def status():
            return json.loads(run('status').stdout)
        print(run('--version').stdout.strip())
        try:
            print(run('on').stdout.strip())
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                data = status()
                if data.get('chats') == 1:
                    break
                time.sleep(.25)
            assert data.get('running') and data.get('chats') == 1, data
            assert not data.get('error'), data.get('error')
            assert data['group_menu']['visible'] and data['visible'][ident]
            assert data['statistics'][ident]['level'] == 1
            assert data['sounds']['enabled'] and data['sounds']['volume'] == 25
            pid = data['pid']
            run('on')
            assert status()['pid'] == pid, 'Duplicate monitor'
            print(json.dumps({'platform':sys.platform,'avatar':True,'menu':True,'xp':True,'single_instance':True}))
        finally:
            try:
                run('off')
            finally:
                if (state / 'app.log').exists():
                    print((state / 'app.log').read_text(encoding='utf-8'))
        assert not status().get('running'), 'Monitor did not stop'


if __name__ == '__main__':
    main()
