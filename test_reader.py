import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from codex_float import Reader, Trace


def event(kind, stamp, turn='a'):
    return json.dumps({'type': 'event_msg', 'timestamp': stamp.isoformat(), 'payload': {'type': kind, 'turn_id': turn}}) + '\n'


class ReaderTests(unittest.TestCase):
    def test_partial_records_and_turn_matching(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace.jsonl'
            now = dt.datetime.now().astimezone()
            path.write_text(event('task_started', now), encoding='utf-8')
            trace = Trace(path)
            trace.read()
            self.assertTrue(trace.active)
            end = event('task_complete', now)
            with path.open('a', encoding='utf-8') as f:
                f.write(event('task_complete', now, 'other') + end[:20])
            trace.read()
            self.assertTrue(trace.active)
            with path.open('a', encoding='utf-8') as f:
                f.write(end[20:])
            trace.read()
            self.assertFalse(trace.active)
            trace.read()
            self.assertFalse(trace.active)

    def test_today_filter_archives_subagents_and_rollover(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            now = dt.datetime.now().astimezone()
            yesterday = now - dt.timedelta(days=1)
            with sqlite3.connect(base / 'state_5.sqlite') as c:
                c.execute('create table threads (id, title, rollout_path, source, archived, updated_at, attached_thread_parent_id)')
                for ident, stamp, archived, source in [('today', now, 0, 'cli'), ('old', yesterday, 0, 'cli'), ('archived', now, 1, 'cli'), ('child', now, 0, '{"subagent":{}}')]:
                    path = base / f'{ident}.jsonl'
                    path.write_text(event('task_started', stamp) + event('task_complete', stamp), encoding='utf-8')
                    c.execute('insert into threads values (?,?,?,?,?,?,null)', (ident, ident, str(path), source, archived, now.timestamp()))
            c.close()
            reader = Reader(base)
            self.assertEqual(reader.snapshot(now), [{'id': 'today', 'title': 'today', 'state': 'sleeping'}])
            self.assertEqual(reader.snapshot(now + dt.timedelta(days=1)), [])


if __name__ == '__main__':
    unittest.main()
