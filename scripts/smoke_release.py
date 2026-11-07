"""Exercise an actual packaged desktop process with synthetic local session data."""
import datetime as dt
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import psutil


def main():
    executable = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix='agentlings-smoke-') as folder:
        root = Path(folder)
        codex = root / 'codex'; codex.mkdir()
        state = root / 'state'
        now = dt.datetime.now(dt.timezone.utc)
        ident = '11111111-2222-4333-8444-555555555555'
        state.mkdir()
        (state / 'starred.json').write_text(json.dumps({ident: {'enabled': True, 'symbol': 'star'}}), encoding='utf-8')
        trace = codex / 'session.jsonl'
        records = [{'timestamp': now.isoformat(), 'type': 'event_msg', 'payload': {'type': event, 'turn_id': 'test'}}
                   for event in ('task_started', 'task_complete')]
        trace.write_text('\n'.join(json.dumps(record) for record in records) + '\n', encoding='utf-8')
        with closing(sqlite3.connect(codex / 'state_5.sqlite')) as db:
            db.execute('CREATE TABLE threads (id,title,cwd,rollout_path,source,archived,updated_at,attached_thread_parent_id)')
            db.execute('INSERT INTO threads VALUES (?,?,?,?,?,0,?,NULL)',
                       (ident, 'Release smoke session', str(root), str(trace), 'cli', now.timestamp()))
            db.commit()
        env = dict(os.environ, AGENTLINGS_STATE_DIR=str(state), CODEX_HOME=str(codex),
                   CLAUDE_CONFIG_DIR=str(root / 'claude'), AGENTLINGS_DISABLE_DISCOVERY='1')
        def run(*args):
            return subprocess.run([executable, *args], env=env, capture_output=True, text=True, timeout=35, check=True)
        def status():
            return json.loads(run('status').stdout)
        print(run('--version').stdout.strip())
        owner = None
        try:
            print(run('on').stdout.strip())
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                data = status()
                if data.get('chats') == 1 and (data.get('starred', {}).get(ident) or {}).get('visible'):
                    break
                time.sleep(.25)
            assert data.get('running') and data.get('chats') == 1, 'Expected exactly one synthetic avatar'
            assert not data.get('error'), data.get('error')
            assert data['group_menu']['visible'] and data['visible'][ident]
            assert data['statistics'][ident]['level'] == 1
            assert data['sounds']['enabled'] and data['sounds']['volume'] == 25
            assert data['capabilities']['app'] == 'Agentlings'
            marker = data['starred'][ident]
            assert marker['visible'] and marker['symbol'] == 'star'
            gap = marker['position'][1] - data['windows'][ident][1] - data['sizes'][ident][1]
            assert gap == 4, f'Top marker must have a 4px gap: {marker}, avatar={data["windows"][ident]}, size={data["sizes"][ident]}'
            pid = data['pid']
            owner = psutil.Process(pid)
            run('on')
            assert status()['pid'] == pid, 'Duplicate monitor'
            alias = Path(executable).with_name('codex-float.cmd' if os.name == 'nt' else 'codex-float')
            alias_command = [str(alias), 'status']
            if os.name == 'nt':
                alias_command = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', *alias_command]
            reply = subprocess.run(alias_command, env=env, capture_output=True, text=True, timeout=15, check=True)
            assert json.loads(reply.stdout)['pid'] == pid, 'Legacy alias uses a different monitor'
            assert data['attention']['pending'] == 1, 'Expected an unread historical result'
            events = [
                {'type': 'task_started', 'turn_id': 'attention'},
                {'type': 'item_completed', 'turn_id': 'attention', 'item': {
                    'id': 'failed-tool', 'type': 'CommandExecution', 'command': 'synthetic-check',
                    'exit_code': 1, 'aggregated_output': 'PRIVATE_SMOKE_OUTPUT'}},
                {'type': 'turn_aborted', 'turn_id': 'attention'},
                {'type': 'task_started', 'turn_id': 'after-interruption'},
            ]
            with trace.open('a', encoding='utf-8') as stream:
                for payload in events:
                    stream.write(json.dumps({'timestamp': dt.datetime.now(dt.timezone.utc).isoformat(),
                                             'type': 'event_msg', 'payload': payload}) + '\n')
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                data = status()
                if data.get('attention', {}).get('pending') == 3:
                    break
                time.sleep(.25)
            assert data.get('attention', {}).get('pending') == 3, 'New error and interruption must remain visible'
            metadata = (state / 'attention.json').read_text(encoding='utf-8')
            assert 'PRIVATE_SMOKE_OUTPUT' not in metadata and 'synthetic-check' not in metadata
            run('off')
            owner.wait(timeout=10)
            (state / 'visibility.json').write_text(json.dumps({'hidden': [ident]}), encoding='utf-8')
            run('on')
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                data = status()
                if data.get('running') and data.get('attention', {}).get('pending') == 3:
                    break
                time.sleep(.25)
            assert data.get('attention', {}).get('pending') == 3, 'Unseen events must survive restart'
            owner = psutil.Process(data['pid'])
            assert not data['visible'][ident] and not data['starred'][ident]['visible']
            assert data['companions'][ident]['visual'] is None, 'Hidden companions must not render animations'
            previous_error = json.loads(metadata)['sessions'][ident]['error_at']
            stamp = dt.datetime.now(dt.timezone.utc)
            with trace.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'timestamp': stamp.isoformat(), 'type': 'event_msg', 'payload': {
                    'type': 'item_completed', 'turn_id': 'after-interruption', 'item': {
                        'id': 'hidden-failure', 'type': 'CommandExecution', 'exit_code': 1}}}) + '\n')
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                observed = json.loads((state / 'attention.json').read_text(encoding='utf-8'))
                if observed['sessions'][ident]['error_at'] > previous_error:
                    break
                time.sleep(.25)
            assert observed['sessions'][ident]['error_at'] == stamp.timestamp(), 'Hidden sessions must still observe new events'
            print(json.dumps({'platform':sys.platform,'avatar':True,'menu':True,'xp':True,
                              'single_instance':True,'legacy_alias':True,'attention_restart':True,
                              'hidden_observation':True}))
        finally:
            try:
                run('off')
                if owner:
                    owner.wait(timeout=10)
            finally:
                if (state / 'app.log').exists():
                    print((state / 'app.log').read_text(encoding='utf-8'))
        assert not status().get('running'), 'Monitor did not stop'


if __name__ == '__main__':
    main()
