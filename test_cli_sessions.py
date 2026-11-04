import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cli_sessions import registrations, session_id, launch
from codex_float import Reader
from test_reader import event


class CliTests(unittest.TestCase):
    def test_registration_liveness_and_session_id_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            (state / 'cli-sessions').mkdir()
            for ident, age in [('live', 1), ('stale', 30)]:
                (state / 'cli-sessions' / f'{ident}.json').write_text(json.dumps({'id': ident, 'running': True, 'heartbeat': time.time() - age}))
            records = registrations(state)
            self.assertTrue(records['live']['live'])
            self.assertFalse(records['stale']['live'])
        with self.assertRaises(ValueError):
            session_id('../../escape')

    def test_cli_filter_includes_today_resumes_but_excludes_desktop(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            now = dt.datetime.now().astimezone()
            yesterday = now - dt.timedelta(days=1)
            c = sqlite3.connect(base / 'state_5.sqlite')
            c.execute('create table threads (id,title,rollout_path,source,archived,updated_at,attached_thread_parent_id)')
            for ident, source, stamp in [('cli', 'cli', now), ('gui', 'vscode', now), ('resumed', 'vscode', yesterday)]:
                path = base / f'{ident}.jsonl'
                path.write_text(event('task_started', stamp) + event('task_complete', stamp), encoding='utf-8')
                c.execute('insert into threads values (?,?,?,?,0,?,null)', (ident, ident, str(path), source, stamp.timestamp()))
            c.commit(); c.close()
            records = {'resumed': {'started_at': now.timestamp(), 'live': True}}
            rows = Reader(base, cli_only=True, registration_loader=lambda: records).snapshot(now)
            self.assertEqual({r['id'] for r in rows}, {'cli', 'resumed'})

    @unittest.skipUnless(os.name == 'nt', 'Windows terminal focus')
    def test_live_session_is_focused_without_starting_a_second_cli(self):
        ident = '11111111-1111-1111-1111-111111111111'
        native = SimpleNamespace(inspect=lambda _: SimpleNamespace(pid=123, title='Codex CLI [token]'), activate=lambda _: None)
        with patch('cli_sessions.thread_info', return_value={}), patch('cli_sessions.registrations', return_value={ident: {'live': True, 'hwnd': 456, 'window_pid': 123, 'token': 'token'}}), patch('window_focus.Windows', return_value=native), patch('cli_sessions.subprocess.Popen') as spawn:
            self.assertEqual(launch(ident), ident)
            spawn.assert_not_called()

    def test_unmanaged_active_turn_is_not_resumed_in_parallel(self):
        ident = '11111111-1111-1111-1111-111111111111'
        with tempfile.TemporaryDirectory() as folder:
            with patch('terminal_discovery.refresh_external'), patch('cli_sessions.STATE', Path(folder)), patch('cli_sessions.thread_info', return_value={'rollout_path': 'unused'}), patch('cli_sessions.registrations', return_value={}), patch('window_focus.Windows'), patch('codex_float.Trace') as trace, patch('cli_sessions.subprocess.Popen') as spawn:
                trace.return_value.active = {'turn-in-progress'}
                with self.assertRaisesRegex(RuntimeError, 'turno activo'):
                    launch(ident)
                spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
