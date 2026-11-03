import datetime as dt
import unittest

from session_activity import Activity
from session_details import details_text


class PreviousResultTests(unittest.TestCase):
    def setUp(self):
        self.activity = Activity()

    def event(self, kind, stamp, turn='first', **extra):
        self.activity.observe({'type': 'event_msg', 'payload': {'type': kind, 'turn_id': turn, **extra}},
            dt.datetime.fromtimestamp(stamp, dt.timezone.utc))

    def message(self, text, stamp, turn='first', phase='final'):
        self.event('item_completed', stamp, turn, item={'type': 'AgentMessage', 'phase': phase, 'content': text})

    def fields(self, state='working'):
        return details_text({'state': state, 'activity': self.activity.summary()}, now=150)

    def test_new_turn_keeps_one_prior_final_separate_from_current_progress(self):
        self.event('task_started', 90)
        self.message('Implemented the search control.', 99)
        self.event('task_complete', 100)
        self.assertEqual(self.fields('sleeping')['previous_result'], '')
        self.event('task_started', 101, 'second')
        self.message('Checking keyboard navigation.', 102, 'second', phase='commentary')
        fields = self.fields()
        self.assertEqual(fields['report'], 'Checking keyboard navigation.')
        self.assertEqual(fields['previous_result'], 'Implemented the search control.')
        self.message('Keyboard navigation is ready.', 110, 'second')
        self.event('task_complete', 111, 'second')
        self.assertEqual(self.fields('sleeping')['previous_result'], '')
        self.event('task_started', 112, 'third')
        self.assertEqual(self.fields()['previous_result'], 'Keyboard navigation is ready.')

    def test_missing_final_is_explicit_and_progress_is_not_presented_as_a_result(self):
        self.event('task_started', 90)
        self.message('Still investigating.', 99, phase='commentary')
        self.event('task_complete', 100)
        self.event('task_started', 101, 'second')
        fields = self.fields()
        self.assertIn('sin un resumen final', fields['previous_result'])
        self.assertNotIn('investigating', fields['previous_result'])

    def test_interrupted_turn_does_not_overwrite_prior_completed_result(self):
        self.event('task_started', 90)
        self.message('First result.', 99)
        self.event('task_complete', 100)
        self.event('task_started', 101, 'second')
        self.event('turn_aborted', 102, 'second')
        self.assertEqual(self.fields('sleeping')['previous_result'], 'First result.')

    def test_late_final_for_completed_turn_is_retained_but_older_turn_cannot_overwrite(self):
        self.event('task_started', 90)
        self.event('task_complete', 100)
        self.message('Late result.', 100.1)
        self.event('task_started', 101, 'second')
        self.message('Stale message.', 102)
        self.assertEqual(self.fields()['previous_result'], 'Late result.')

    def test_prior_result_stays_bounded_and_uses_the_same_sanitization(self):
        self.event('task_started', 90)
        self.message('password=DO_NOT_DISPLAY', 99)
        self.event('task_complete', 100)
        self.event('task_started', 101, 'second')
        self.assertNotIn('DO_NOT_DISPLAY', repr(self.activity.summary()))
        self.assertIn('Contenido sensible omitido', self.fields()['previous_result'])
        self.message('Long prose. ' * 100, 110, 'second')
        self.event('task_complete', 111, 'second')
        self.assertLessEqual(len(self.activity.last_result), 180)


if __name__ == '__main__':
    unittest.main()
