import json
import datetime as dt
import unittest

from session_attention import AttentionInbox, LIMIT
from session_activity import Activity


def chat(ident='a', phase='Analizando', state='working', error=0, finished=0):
    return {'id': ident, 'title': 'Example session', 'provider': 'codex', 'state': state,
            'activity': {'phase': phase, 'finished_at': finished,
                         'actions': [{'at': error, 'outcome': 'error'}] if error else []}}


def entries(*chats):
    return {item['id']: {'chat': item} for item in chats}


class AttentionTests(unittest.TestCase):
    def test_fast_error_and_interruption_survive_action_eviction_and_next_turn(self):
        activity = Activity()
        inbox = AttentionInbox()
        inbox.observe([chat()], 10)
        def event(kind, stamp, turn='first'):
            activity.observe({'type': 'event_msg', 'payload': {'type': kind, 'turn_id': turn}},
                             dt.datetime.fromtimestamp(stamp, dt.timezone.utc))
        event('task_started', 11)
        activity.add_action('Tool', dt.datetime.fromtimestamp(12, dt.timezone.utc), 'error', 'failed')
        for stamp in range(13, 20):
            activity.add_action('Tool', dt.datetime.fromtimestamp(stamp, dt.timezone.utc), 'ok', str(stamp))
        self.assertFalse(any(item['outcome'] == 'error' for item in activity.actions))
        event('turn_aborted', 20)
        event('task_started', 21, 'second')
        current = dict(chat(), activity=activity.summary())
        inbox.observe([current], 22)
        self.assertEqual([(row['kind'], row['at']) for row in inbox.rows(entries(current), {}, 23)],
                         [('interrupted', 20), ('error', 12)])

    def test_first_discovery_baselines_history_but_new_errors_survive_recovery_and_restart(self):
        inbox = AttentionInbox()
        inbox.observe([chat(error=10)], 20)
        self.assertEqual(inbox.rows(entries(chat()), {}, 20), [])
        self.assertFalse(inbox.observe([chat(error=10)], 21))
        self.assertTrue(inbox.observe([chat(error=25)], 26))
        inbox.observe([chat()], 27)
        restored = AttentionInbox(json.loads(json.dumps(inbox.snapshot())))
        self.assertFalse(restored.observe([chat()], 28))
        rows = restored.rows(entries(chat()), {}, 28)
        self.assertEqual([(r['kind'], r['at']) for r in rows], [('error', 25)])
        self.assertTrue(restored.acknowledge('a', 'error', 25))
        self.assertEqual(AttentionInbox(restored.snapshot()).rows(entries(chat()), {}, 29), [])

    def test_stale_selection_cannot_acknowledge_a_newer_failure(self):
        inbox = AttentionInbox()
        inbox.observe([chat()], 10)
        inbox.observe([chat(error=20)], 21)
        inbox.observe([chat(error=30)], 31)
        self.assertFalse(inbox.acknowledge('a', 'error', 20))
        self.assertEqual(len(inbox.rows(entries(chat()), {}, 32)), 1)

    def test_input_is_explicit_and_seen_does_not_resolve_it(self):
        inbox = AttentionInbox()
        waiting = chat(phase='Esperando una herramienta')
        inbox.observe([waiting], 10)
        self.assertEqual(inbox.rows(entries(waiting), {}, 11), [])
        asking = chat(phase='Esperando intervención')
        inbox.observe([asking], 20)
        inbox.observe([asking], 21)
        row = inbox.rows(entries(asking), {}, 22)[0]
        self.assertEqual((row['kind'], row['at']), ('input', 20))
        self.assertFalse(inbox.acknowledge('a', 'input', 20))
        unknown = chat(state='unknown')
        inbox.observe([unknown], 23)
        self.assertTrue(inbox.rows(entries(unknown), {}, 24)[0]['stale'])
        inbox.observe([chat()], 25)
        self.assertEqual(inbox.rows(entries(chat()), {}, 26), [])

    def test_interruptions_and_results_are_distinct_and_ordered_after_input(self):
        inbox = AttentionInbox()
        inbox.observe([chat()], 10)
        interrupted = chat(phase='Turno interrumpido', state='sleeping', finished=20, error=18)
        asking = chat('b', phase='Esperando intervención')
        inbox.observe([interrupted, asking], 21)
        notice = {'a': {'completed_at': 15, 'acknowledged_at': 0}}
        rows = inbox.rows(entries(interrupted, asking), notice, 22)
        self.assertEqual([r['kind'] for r in rows], ['input', 'interrupted', 'error', 'result'])
        self.assertEqual(inbox.count(entries(interrupted, asking), notice), len(rows))
        self.assertTrue(inbox.acknowledge('a', 'interrupted', 20))
        notice['a']['acknowledged_at'] = 15
        self.assertEqual([r['kind'] for r in inbox.rows(entries(interrupted), notice, 23)], ['error'])

    def test_unavailable_sessions_retain_unseen_events_without_open_action(self):
        inbox = AttentionInbox()
        inbox.observe([chat()], 10)
        inbox.observe([chat(error=20)], 21)
        row = inbox.rows({}, {}, 22)[0]
        self.assertFalse(row['available'])
        self.assertTrue(row['stale'])
        self.assertFalse(inbox.rows(entries(chat()), {}, 22, available=False)[0]['available'])

    def test_persistence_is_bounded_validated_and_never_contains_prose(self):
        saved = {'sessions': {'bad': {'error_at': float('nan'), 'error_seen': -1, 'title': 'secret'},
                              '../path': {'error_at': 10}, 'wrong': 'secret'}}
        inbox = AttentionInbox(saved)
        self.assertNotIn('../path', inbox.records)
        for n in range(LIMIT + 20):
            item = chat(str(n), error=n + 1)
            item['title'] = 'password=DO_NOT_STORE'
            inbox.observe([item], LIMIT + 30)
        data = json.dumps(inbox.snapshot(), allow_nan=False)
        self.assertLessEqual(len(inbox.records), LIMIT)
        self.assertNotIn('secret', data)
        self.assertNotIn('DO_NOT_STORE', data)
        self.assertNotIn('title', data)


if __name__ == '__main__':
    unittest.main()
