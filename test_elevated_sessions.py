import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from elevated_activity import ClaudeActivity
from elevated_sessions import collect, describe, load_feed
from session_status import status_code


def process(pid=20, uid=0, name='codex', tty='/dev/pts/2', parents=(), birth=10):
    return SimpleNamespace(pid=pid, name=lambda: name, uids=lambda: SimpleNamespace(real=uid),
        terminal=lambda: tty, parents=lambda: list(parents), create_time=lambda: birth)


@unittest.skipUnless(os.name == 'posix', 'Optional POSIX elevated-process observer')
class ObserverTests(unittest.TestCase):
    def setUp(self):
        terminal = patch('elevated_sessions.controlling_terminal', side_effect=lambda p: p.terminal())
        terminal.start()
        self.addCleanup(terminal.stop)

    def test_only_root_cli_under_target_users_terminal_is_exported(self):
        terminal = process(10, uid=1000, name='kitty')
        accepted = process(parents=[terminal])
        rejected = [process(21, uid=1000, parents=[terminal]), process(22, tty=None, parents=[terminal]),
            process(23, parents=[process(11, uid=1001, name='kitty')]),
            process(24, parents=[process(12, uid=1000, name='sshd')]),
            process(25, name='bash', parents=[terminal])]
        data = collect(1000, [accepted, *rejected], now=100)
        self.assertEqual([row['pid'] for row in data['sessions']], [20])
        self.assertEqual(set(data['sessions'][0]),
            {'pid', 'created_at', 'provider', 'terminal_pid', 'terminal_created_at', 'shell_pid'})

    def test_shell_identity_comes_from_direct_terminal_child(self):
        terminal = process(10, uid=1000, name='kitty')
        shell = process(11, uid=1000, name='bash')
        root_shell = process(12, name='bash')
        row = describe(process(parents=[root_shell, shell, terminal]), 1000)
        self.assertEqual(row['shell_pid'], 11)

    def test_malformed_activity_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.data()
            data['sessions'][0]['chat'] = {'state': 'working'}
            with self.assertRaises(ValueError):
                self.load(self.write(folder, data))

    def write(self, folder, data):
        path = Path(folder)/'sessions.json'
        path.write_text(json.dumps(data))
        path.chmod(0o600)
        return path

    def data(self):
        return collect(1000, [process(parents=[process(10, uid=1000, name='kitty')])], now=100)

    def load(self, path, **kwargs):
        return load_feed(path, uid=1000, now=101, trusted_uid=os.getuid(), **kwargs)

    def test_live_process_is_unknown_not_sleeping_or_completed(self):
        with tempfile.TemporaryDirectory() as folder:
            chat = self.load(self.write(folder, self.data()))[0]
        self.assertEqual(status_code(chat), 'unknown')
        self.assertTrue(chat['terminal']['live'])
        self.assertEqual(chat['activity'], {})
        self.assertTrue(chat['terminal']['elevated'])

    def test_pid_reuse_gets_a_new_avatar_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.data()
            first = self.load(self.write(folder, data))[0]['id']
            data['sessions'][0]['created_at'] += 1
            second = self.load(self.write(folder, data))[0]['id']
            self.assertNotEqual(first, second)

    def test_expired_future_wrong_user_and_duplicate_snapshots_are_rejected(self):
        for update in ({'heartbeat': 80}, {'heartbeat': 105}, {'heartbeat': float('nan')}, {'uid': 2000}, {'version': 9}):
            with self.subTest(update=update), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    self.load(self.write(folder, dict(self.data(), **update)))
        with tempfile.TemporaryDirectory() as folder:
            data = self.data(); data['sessions'] *= 2
            with self.assertRaises(ValueError):
                self.load(self.write(folder, data))

    def test_writable_file_or_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, self.data())
            path.chmod(0o666)
            with self.assertRaises(ValueError):
                self.load(path)
            path.chmod(0o600); Path(folder).chmod(0o777)
            with self.assertRaises(ValueError):
                self.load(path)
            Path(folder).chmod(0o700)

    @unittest.skipUnless(hasattr(os, 'O_NOFOLLOW'), 'POSIX file ownership and symlinks')
    def test_symlink_and_fifo_cannot_redirect_or_block_the_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, self.data())
            link = Path(folder)/'link'; link.symlink_to(path)
            with self.assertRaises(OSError):
                self.load(link)
            fifo = Path(folder)/'fifo'; os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                self.load(fifo)

    def test_vanished_process_is_removed_on_next_observation(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(len(self.load(self.write(folder, self.data()))), 1)
            self.assertEqual(self.load(self.write(folder, collect(1000, [], now=100))), [])


if __name__ == '__main__':
    unittest.main()


CLAUDE_SID = '11111111-2222-4333-8444-555555555555'


@unittest.skipUnless(os.name == 'posix', 'Optional POSIX elevated-process observer')
class ClaudeActivityTests(unittest.TestCase):
    def setUp(self):
        ticks = patch('claude_trace.linux_start_ticks', return_value=4242)
        ticks.start()
        self.addCleanup(ticks.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name)
        (self.home/'sessions').mkdir()
        (self.home/'projects'/'-home-user').mkdir(parents=True)

    def record(self, provider='claude'):
        return {'pid': 20, 'created_at': 10, 'provider': provider, 'terminal_pid': 10,
                'terminal_created_at': 5, 'shell_pid': 11}

    def session(self, **extra):
        data = {'pid': 20, 'sessionId': CLAUDE_SID, 'procStart': '4242', 'kind': 'interactive',
                'entrypoint': 'cli', 'cwd': '/home/user/project', 'name': 'Services Offering', **extra}
        (self.home/'sessions'/'20.json').write_text(json.dumps(data))

    def transcript(self, *records):
        path = self.home/'projects'/'-home-user'/f'{CLAUDE_SID}.jsonl'
        path.write_text(''.join(json.dumps(r) + '\n' for r in records))

    def enrich(self, *records):
        ClaudeActivity(self.home).enrich(list(records))
        return records

    def test_busy_session_reports_working_with_title_and_project(self):
        self.session(status='busy')
        self.transcript({'type': 'user', 'sessionId': CLAUDE_SID, 'uuid': 'u1',
                         'timestamp': '2026-11-21T10:00:00Z', 'message': {'content': 'Refina la oferta'}})
        row, = self.enrich(self.record())
        chat = row['chat']
        self.assertEqual((chat['id'], chat['state'], chat['project']), (f'claude:{CLAUDE_SID}', 'working', 'project'))
        self.assertEqual(chat['title'], 'Services Offering')

    def test_user_given_name_wins_over_generated_title(self):
        self.transcript({'type': 'ai-title', 'sessionId': CLAUDE_SID, 'aiTitle': 'Generated title'})
        self.session(status='busy')
        row, = self.enrich(self.record())
        self.assertEqual(row['chat']['title'], 'Generated title')
        self.session(status='busy', nameSource='user')
        row, = self.enrich(self.record())
        self.assertEqual(row['chat']['title'], 'Services Offering')

    def test_waiting_and_idle_states(self):
        self.session(status='waiting_for_permission')
        row, = self.enrich(self.record())
        self.assertEqual((row['chat']['state'], row['chat']['activity']['phase']), ('working', 'Esperando intervención'))
        self.session(status='idle')
        row, = self.enrich(self.record())
        self.assertEqual(row['chat']['state'], 'sleeping')

    def test_unverifiable_sessions_stay_unknown(self):
        self.session(status='busy', procStart='9999')  # recycled pid: start ticks differ
        codex, claude = self.enrich(self.record('codex'), self.record())
        self.assertNotIn('chat', claude)
        self.assertNotIn('chat', codex)
        (self.home/'sessions'/'20.json').unlink()
        row, = self.enrich(self.record())
        self.assertNotIn('chat', row)

    def test_unknown_status_without_transcript_is_not_guessed(self):
        self.session(status='something-new')
        row, = self.enrich(self.record())
        self.assertNotIn('chat', row)

    def test_enriched_feed_passes_desktop_validation(self):
        self.session(status='busy')
        data = {'version': 1, 'uid': 1000, 'heartbeat': 100, 'sessions': list(self.enrich(self.record()))}
        path = self.home/'feed'/'sessions.json'
        path.parent.mkdir(mode=0o750)
        path.write_text(json.dumps(data))
        path.chmod(0o600)
        rows = load_feed(path, 1000, now=101, trusted_uid=os.getuid())
        self.assertEqual((rows[0]['provider'], rows[0]['state']), ('claude', 'working'))

