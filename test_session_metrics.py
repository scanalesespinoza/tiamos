import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from claude_sessions import ClaudeTrace
from codex_float import Trace
from session_activity import Activity
from session_metrics import SessionMetrics, level_progress, profile_text


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
        self.activity = Activity()

    def event(self, kind, seconds=0, **payload):
        self.activity.observe({'type': 'event_msg', 'payload': {'type': kind, **payload}},
                              self.now + dt.timedelta(seconds=seconds))

    def action(self, ident, command='git status', code=0, **extra):
        self.event('item_completed', item={'id': ident, 'type': 'CommandExecution',
                   'command': command, 'exit_code': code, **extra})

    def test_actual_outcomes_unknowns_and_single_completion(self):
        self.event('task_started', turn_id='turn')
        self.action('good')
        self.action('bad', code=1)
        self.action('unknown', code=None)
        self.action('test', command='python -m unittest')
        self.event('item_completed', item={'id': 'edit', 'type': 'FileChange', 'status': 'completed'})
        self.event('task_complete', 60, turn_id='turn')
        self.event('task_completed', 61, turn_id='turn')
        total = self.activity.summary()['stats']['total']
        self.assertEqual((total['actions'], total['ok'], total['errors'], total['unknown']), (5, 3, 1, 1))
        self.assertEqual((total['validations'], total['validations_ok'], total['edits']), (1, 1, 1))
        self.assertEqual((total['completed'], total['completed_seconds'], total['xp']), (1, 60, 20))

    def test_waits_errors_and_out_of_turn_items_do_not_farm_xp(self):
        self.action('orphan')
        self.event('task_started', turn_id='turn')
        self.activity.add_action('Esperando una herramienta', self.now, 'ok', 'wait')
        self.event('item_completed', item={'id': 'sleep', 'type': 'Extension', 'kind': 'clock.sleep', 'durationMs': 20000})
        self.activity.add_action('Error de Claude', self.now, 'error', 'api')
        self.action('bad', code=1)
        self.event('turn_aborted', 2, turn_id='turn')
        self.event('turn_aborted', 3, turn_id='turn')
        total = self.activity.summary()['stats']['total']
        self.assertEqual(total['xp'], 0)
        self.assertEqual(total['actions'], 1)
        self.assertEqual((total['waits'], total['api_errors'], total['interrupted']), (2, 1, 1))

    def test_caps_volume_per_turn_and_handles_duplicates_and_wrong_turn(self):
        self.event('task_started', turn_id='turn')
        for i in range(80):
            self.action(str(i))
            self.action(str(i))
        self.event('task_started', turn_id='turn')
        self.action('79')
        self.event('task_complete', turn_id='other')
        self.assertEqual(self.activity.summary()['stats']['xp'], 50)
        self.event('task_complete', 5, turn_id='turn')
        self.event('task_started', 6, turn_id='second')
        self.action('new')
        self.event('task_complete', 10, turn_id='second')
        stats = self.activity.summary()['stats']
        self.assertEqual(stats['xp'], 72)
        self.assertEqual(stats['total']['actions'], 81)
        self.assertEqual(stats['total']['completed'], 2)

    def test_local_day_rollover_keeps_lifetime_and_bounded_storage(self):
        metrics = SessionMetrics()
        before = self.now.replace(hour=23, minute=59)
        after = before + dt.timedelta(minutes=2)
        metrics.start(before, 'overnight')
        metrics.action('Edición de archivos', 'ok', before)
        metrics.finish(after, True)
        self.assertEqual(metrics.summary(before)['today']['xp'], 2)
        self.assertEqual(metrics.summary(after)['today']['xp'], 10)
        self.assertEqual(metrics.summary(after)['total']['xp'], 12)
        for day in range(20):
            stamp = after + dt.timedelta(days=day)
            metrics.start(stamp, f'day-{day}')
            metrics.finish(stamp, True)
        self.assertLessEqual(len(metrics.days), 8)
        self.assertEqual(metrics.summary(stamp + dt.timedelta(days=1))['today']['xp'], 0)
        self.assertEqual(metrics.total['xp'], 212)

    def test_level_thresholds_and_profile_caveats(self):
        for xp, level, progress in [(0, 1, 0), (99, 1, 99), (100, 2, 0), (299, 2, 199), (300, 3, 0), (600, 4, 0)]:
            value = level_progress(xp)
            self.assertEqual((value['level'], value['progress']), (level, progress))
            self.assertLess(value['progress'], value['needed'])
        fields = profile_text(self.activity.summary()['stats'])
        self.assertIn('sin resultados conocidos', fields['profile_quality'])
        self.assertIn('no certifica la tarea', fields['profile_note'])
        self.assertNotIn('100%', str(fields))

    def test_numeric_stats_exclude_commands_outputs_objectives_and_ids(self):
        self.event('task_started', turn_id='PRIVATE_TURN')
        self.event('user_message', message='PRIVATE_REQUEST')
        self.action('PRIVATE_ID', command='PRIVATE_COMMAND', aggregated_output='PRIVATE_OUTPUT')
        self.assertNotIn('PRIVATE', json.dumps(self.activity.summary()['stats']))

    def test_codex_replay_poll_and_restart_do_not_multiply_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.jsonl'
            records = [
                {'type': 'task_started', 'turn_id': 'a'},
                {'type': 'item_completed', 'item': {'type': 'CommandExecution', 'id': 'tool', 'exit_code': 0}},
                {'type': 'task_complete', 'turn_id': 'a'},
                {'type': 'task_completed', 'turn_id': 'a'},
            ]
            path.write_text(''.join(json.dumps({'type': 'event_msg', 'timestamp': self.now.isoformat(),
                                                'payload': payload}) + '\n' for payload in records), encoding='utf-8')
            trace = Trace(path)
            trace.read()
            expected = trace.activity.summary()['stats']
            trace.read()
            self.assertEqual(trace.activity.summary()['stats'], expected)
            restarted = Trace(path)
            restarted.read()
            self.assertEqual(restarted.activity.summary()['stats'], expected)
            self.assertEqual(expected['xp'], 12)
            # Truncated source reflects available history, never adds it again.
            path.write_text('', encoding='utf-8')
            trace.read()
            self.assertEqual(trace.activity.summary()['stats']['xp'], 0)

    def test_claude_adapter_uses_same_rules_and_deduplicates_end_signals(self):
        trace = ClaudeTrace('unused', 'session')
        def emit(kind, ident, message=None, **extra):
            trace.observe({'type': kind, 'uuid': ident, 'sessionId': 'session',
                           'timestamp': self.now.isoformat(), 'message': message or {}, **extra})
        emit('user', 'request', {'content': 'Work'})
        emit('assistant', 'call', {'content': [{'type': 'tool_use', 'id': 'tool', 'name': 'Bash',
                                               'input': {'command': 'python -m unittest'}}]})
        result = {'content': [{'type': 'tool_result', 'tool_use_id': 'tool', 'content': 'PRIVATE'}]}
        emit('user', 'result', result)
        emit('user', 'duplicate', result)
        emit('assistant', 'final', {'content': 'Done', 'stop_reason': 'end_turn'})
        emit('system', 'duration', subtype='turn_duration')
        total = trace.activity.summary()['stats']['total']
        self.assertEqual((total['xp'], total['actions'], total['validations_ok'], total['completed']), (15, 1, 1, 1))


if __name__ == '__main__':
    unittest.main()
