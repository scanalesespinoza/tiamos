import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from avatar_personality import Notices, provider_theme, render_frames
from claude_sessions import ClaudeSessions, ClaudeTrace, launch_claude, valid_session
from terminal_discovery import match_session
from codex_float import Reader

SID = '11111111-2222-4333-8444-555555555555'


def record(kind, stamp, **kwargs):
    return {'type': kind, 'sessionId': SID, 'timestamp': dt.datetime.fromtimestamp(stamp, dt.timezone.utc).isoformat(), **kwargs}


class ClaudeTests(unittest.TestCase):
    def test_metadata_rejects_recycled_pids_and_noninteractive_clients(self):
        client = {'pid': 10, 'created_at': 100}
        metadata = {'pid': 10, 'sessionId': SID, 'procStart': str(116444736000000000 + 100 * 10000000),
            'kind': 'interactive', 'entrypoint': 'cli'}
        self.assertTrue(valid_session(metadata, client))
        self.assertFalse(valid_session(metadata, dict(client, created_at=200)))
        self.assertFalse(valid_session(dict(metadata, kind='background'), client))
        self.assertFalse(valid_session(dict(metadata, sessionId='invalid'), client))

    def test_turn_lifecycle_actions_final_result_and_privacy(self):
        trace = ClaudeTrace('unused', SID)
        trace.observe(record('user', 100, message={'content': 'Improve the search control'}))
        self.assertTrue(trace.active)
        trace.observe(record('assistant', 101, message={'content': [
            {'type': 'thinking', 'thinking': 'PRIVATE_REASONING'},
            {'type': 'tool_use', 'id': 'tool-a', 'name': 'Bash', 'input': {'command': 'pytest SECRET_ARGUMENT'}}]}))
        self.assertEqual(trace.activity.phase, 'Pruebas y validación')
        trace.observe(record('user', 102, message={'content': [
            {'type': 'tool_result', 'tool_use_id': 'tool-a', 'content': 'PRIVATE_TOOL_OUTPUT', 'is_error': True}]}))
        self.assertEqual(trace.activity.actions[0]['outcome'], 'error')
        self.assertEqual(trace.activity.summary()['verification']['check_outcome'], 'error')
        self.assertEqual(trace.activity.summary()['verification']['check_kind'], 'Pruebas/validación')
        self.assertEqual(trace.activity.objective, 'Improve the search control')
        trace.observe(record('assistant', 103, message={'content': [{'type': 'text', 'text': 'Reported result.'}], 'stop_reason': 'end_turn'}))
        self.assertFalse(trace.active)
        self.assertEqual(trace.activity.final, 'Reported result.')
        self.assertEqual(trace.activity.last_completed_at, 103)
        self.assertTrue(trace.activity.last_completion_error)
        retained = repr(trace.__dict__) + repr(trace.activity.summary())
        for secret in ['PRIVATE_REASONING', 'PRIVATE_TOOL_OUTPUT', 'SECRET_ARGUMENT']:
            self.assertNotIn(secret, retained)
        trace.observe(record('system', 104, subtype='turn_duration'))
        self.assertEqual(trace.activity.finished_at, 103)

    def test_duration_record_finishes_messages_without_a_stop_reason(self):
        trace = ClaudeTrace('unused', SID)
        trace.observe(record('user', 100, message={'content': 'Do the task'}))
        trace.observe(record('assistant', 101, message={'content': [{'type': 'text', 'text': 'Finished.'}], 'stop_reason': None}))
        self.assertTrue(trace.active)
        trace.observe(record('system', 102, subtype='turn_duration'))
        self.assertFalse(trace.active)
        self.assertEqual(trace.activity.last_result, 'Finished.')
        trace.observe(record('user', 103, message={'content': 'Next task'}))
        self.assertEqual(trace.activity.last_result, 'Finished.')

    def test_api_failure_does_not_create_successful_completion_notice(self):
        trace = ClaudeTrace('unused', SID)
        trace.observe(record('user', 100, message={'content': 'Do the task'}))
        trace.observe(record('assistant', 101, isApiErrorMessage=True,
            message={'content': [{'type': 'text', 'text': 'API request failed'}], 'stop_reason': 'stop_sequence'}))
        trace.observe(record('system', 102, subtype='turn_duration'))
        self.assertEqual(trace.activity.phase, 'Turno interrumpido')
        self.assertEqual(trace.activity.actions[0]['outcome'], 'error')
        notices = Notices(); notices.observe([], 99)
        self.assertEqual(notices.observe([{'id': 'claude:' + SID, 'activity': trace.activity.summary()}], 103), (False, set()))

    def test_sidechains_metadata_and_other_sessions_do_not_start_turns(self):
        trace = ClaudeTrace('unused', SID)
        for fields in [{'isSidechain': True}, {'isMeta': True}, {'sessionId': 'other'}]:
            trace.observe(record('user', 100, message={'content': 'Ignore this'}, **fields))
        self.assertFalse(trace.active)
        self.assertEqual(trace.activity.objective, '')

    def test_interruptions_do_not_claim_completion(self):
        trace = ClaudeTrace('unused', SID)
        trace.observe(record('user', 100, message={'content': 'Work'}))
        trace.observe(record('user', 101, message={'content': '[Request interrupted by user]'}))
        self.assertFalse(trace.active)
        self.assertIsNone(trace.activity.last_completed_at)
        self.assertEqual(trace.activity.objective, 'Work')

    def test_partial_records_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace.jsonl'
            line = json.dumps(record('user', 100, message={'content': 'Work'})) + '\n'
            path.write_text(line[:30])
            trace = ClaudeTrace(path, SID); trace.read()
            self.assertFalse(trace.active)
            path.write_text(line); trace.read()
            self.assertTrue(trace.active)
            path.write_text(''); trace.read()
            self.assertFalse(trace.active)

    def test_auto_and_custom_titles_without_timestamps(self):
        trace = ClaudeTrace('unused', SID)
        trace.observe({'type': 'ai-title', 'sessionId': SID, 'aiTitle': 'Review the pull request'})
        self.assertEqual(trace.title, 'Review the pull request')
        trace.observe({'type': 'custom-title', 'sessionId': SID, 'customTitle': 'My session'})
        trace.observe({'type': 'ai-title', 'sessionId': SID, 'aiTitle': 'Later automatic title'})
        self.assertEqual(trace.title, 'My session')

    def test_metadata_discovers_new_transcript_keeps_closed_today_and_expires_tomorrow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / 'claude'; (config / 'sessions').mkdir(parents=True)
            now = dt.datetime.now().astimezone()
            client = {'provider': 'claude', 'pid': 10, 'created_at': 100, 'cwd': str(root), 'config_dir': str(config)}
            metadata = {'pid': 10, 'sessionId': SID, 'procStart': str(116444736000000000 + 100 * 10000000),
                'kind': 'interactive', 'entrypoint': 'cli', 'cwd': str(root), 'status': 'idle'}
            registration = config / 'sessions' / '10.json'
            registration.write_text(json.dumps(metadata))
            sessions = ClaudeSessions(root / 'state')
            sessions.metadata([client], now)
            self.assertEqual(sessions.snapshot({})[0]['state'], 'sleeping')
            folder = config / 'projects' / 'encoded'; folder.mkdir(parents=True)
            transcript = folder / f'{SID}.jsonl'
            transcript.write_text(json.dumps(record('user', now.timestamp(), message={'content': 'Start work'})) + '\n')
            metadata.update(status='working', statusUpdatedAt=int(now.timestamp()*1000))
            registration.write_text(json.dumps(metadata))
            sessions.metadata([client], now)
            self.assertEqual(sessions.snapshot({})[0]['state'], 'working')
            self.assertEqual(sessions.snapshot({})[0]['activity']['objective'], 'Start work')
            sessions.metadata([], now)
            self.assertFalse(sessions.snapshot({})[0]['terminal']['live'])
            sessions.metadata([], now + dt.timedelta(days=1))
            self.assertEqual(sessions.snapshot({}), [])

    def test_claude_discovery_does_not_require_a_codex_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = Reader(Path(tmp), cli_only=True, registration_loader=lambda: {})
            reader.claude = SimpleNamespace(metadata=lambda *_: [], snapshot=lambda _: [{'id': 'claude:' + SID}])
            reader.discovery = SimpleNamespace(update=lambda *a, **kw: {})
            with patch('terminal_discovery.native_clients', return_value=[]):
                self.assertEqual(reader.snapshot(), [{'id': 'claude:' + SID}])

    def test_provider_separation_for_codex_and_claude_in_same_directory(self):
        threads = [{'id': 'codex-id', 'provider': 'codex', 'cwd': 'D:\\project', 'name': 'Same'},
            {'id': 'claude:' + SID, 'provider': 'claude', 'cwd': 'D:\\project', 'name': 'Same'}]
        for provider, expected in [('codex', 'codex-id'), ('claude', 'claude:' + SID)]:
            self.assertEqual(match_session({'provider': provider, 'workspace': 'D:\\project', 'title': 'Same'},
                threads, {'d:\\project': 1}), expected)

    def test_live_claude_cannot_be_resumed_as_a_duplicate(self):
        with patch('claude_sessions.subprocess.Popen') as launch:
            with self.assertRaises(RuntimeError):
                launch_claude({'terminal': {'live': True}})
            launch.assert_not_called()

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows Terminal launch')
    def test_closed_claude_resume_uses_claude_executable_and_exact_session_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('claude_sessions.STATE', Path(tmp)), patch('terminal_discovery.native_clients', return_value=[]), \
                 patch('claude_sessions.claude_executable', return_value='C:\\Claude\\claude.exe'), \
                 patch('claude_sessions.shutil.which', return_value='C:\\Windows\\wt.exe'), \
                 patch('claude_sessions.subprocess.Popen') as launch:
                chat = {'session_id': SID, 'cwd': tmp, 'terminal': {'live': False}}
                launch_claude(chat)
                launch_claude(chat)
                launch.assert_called_once()
                command = launch.call_args.args[0]
                self.assertEqual(command[-3:], ['C:\\Claude\\claude.exe', '--resume', SID])
                self.assertEqual(launch.call_args.kwargs['cwd'], str(Path(tmp).resolve()))

    def test_provider_backgrounds_are_distinct_and_fill_each_animation(self):
        for provider, color in [('codex', '#24364b'), ('claude', '#493326')]:
            theme = provider_theme(provider)
            self.assertEqual(theme['background'], color)
            for state in ['working', 'sleeping', 'waiting']:
                frame = render_frames(state, '#77e4c8', background=color)[0]
                expected = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
                self.assertEqual(frame.getpixel((0, 0)), expected)


if __name__ == '__main__':
    unittest.main()
