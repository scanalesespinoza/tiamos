import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from claude_sessions import ClaudeSessions
from codex_float import Reader
from session_history import BLOCK, claude_record, codex_history, history_pin
from test_reader import event

SID = '11111111-2222-4333-8444-555555555555'


class HistoryTests(unittest.TestCase):
    def test_codex_history_is_available_without_promoting_old_sessions_until_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            now = dt.datetime.now().astimezone()
            old = now - dt.timedelta(days=5)
            path = root / 'trace.jsonl'
            path.write_text(event('task_started', old) + event('task_complete', old))
            with sqlite3.connect(root / 'state_5.sqlite') as db:
                db.execute('create table threads (id,title,cwd,rollout_path,source,archived,updated_at,attached_thread_parent_id)')
                db.execute('insert into threads values (?,?,?,?,?,?,?,null)',
                           (SID, 'Old session', folder, str(path), 'vscode', 0, old.timestamp()))
            db.close()
            records = codex_history(root)
            self.assertEqual([r['id'] for r in records], [SID])
            included = {}
            reader = Reader(root, cli_only=True, registration_loader=lambda: {}, included_loader=included.copy)
            self.assertEqual(reader.snapshot(now), [])
            included[SID] = history_pin(records[0])
            with patch('cli_sessions.launch') as launch:
                chats = reader.snapshot(now)
                launch.assert_not_called()
            self.assertEqual(chats[0]['id'], SID)
            self.assertFalse(chats[0]['terminal']['live'])
            self.assertEqual(chats[0]['state'], 'sleeping')
            included.clear()
            self.assertEqual(reader.snapshot(now), [])

    def test_claude_bounded_metadata_scan_ignores_prose_and_handles_large_middle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / f'{SID}.jsonl'
            head = {'sessionId': SID, 'type': 'user', 'cwd': folder, 'message': {'content': 'PRIVATE PROSE'}}
            title = {'sessionId': SID, 'type': 'custom-title', 'customTitle': 'Previous work'}
            path.write_text(json.dumps(head) + '\n' + 'X' * (3 * BLOCK) + '\n' + json.dumps(title) + '\n')
            record = claude_record(path, root, 100)
            self.assertEqual(record['title'], 'Previous work')
            self.assertEqual(record['id'], 'claude:' + SID)
            self.assertNotIn('PRIVATE', json.dumps(record))
            self.assertNotIn('title', history_pin(record))
            path.write_text(json.dumps(dict(head, isSidechain=True)) + '\n')
            self.assertIsNone(claude_record(path, root, 100))

    def test_selected_old_claude_survives_day_filter_then_can_return_to_today(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / 'projects' / 'example'
            project.mkdir(parents=True)
            now = dt.datetime.now().astimezone()
            old = now - dt.timedelta(days=3)
            path = project / f'{SID}.jsonl'
            path.write_text(json.dumps({'sessionId': SID, 'type': 'user', 'cwd': folder,
                                        'timestamp': old.isoformat(), 'uuid': 'turn', 'message': {'content': 'Old work'}}) + '\n')
            record = claude_record(path, root, old.timestamp())
            included = {record['id']: history_pin(record)}
            sessions = ClaudeSessions(root / 'state')
            sessions.metadata([], now, included)
            self.assertEqual(sessions.snapshot({})[0]['id'], record['id'])
            self.assertFalse(sessions.snapshot({})[0]['terminal']['live'])
            sessions.metadata([], now, {})
            self.assertEqual(sessions.snapshot({}), [])


if __name__ == '__main__':
    unittest.main()
