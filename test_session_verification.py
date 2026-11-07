import datetime as dt
import json
import unittest

from session_activity import Activity
from session_details import details_text
from session_verification import VerificationEvidence, verification_text


def stamp(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc)


class VerificationTests(unittest.TestCase):
    def test_edits_after_check_are_explicit_and_next_check_updates_the_evidence(self):
        evidence = VerificationEvidence()
        evidence.observe('Edición de archivos', 'ok', stamp(10))
        self.assertIn('aún no se observó', verification_text(evidence.summary()))
        evidence.observe('Pruebas y validación', 'ok', stamp(20))
        self.assertFalse(evidence.summary()['edits_after_check'])
        self.assertIn('informó éxito', verification_text(evidence.summary()))
        evidence.observe('Edición de archivos', 'info', stamp(30))
        self.assertTrue(evidence.summary()['edits_after_check'])
        self.assertIn('edición posteriores', verification_text(evidence.summary()))
        evidence.observe('Pruebas y validación', 'error', stamp(40))
        self.assertFalse(evidence.summary()['edits_after_check'])
        self.assertIn('informó un error', verification_text(evidence.summary()))
        self.assertNotIn('éxito', verification_text(evidence.summary()))

    def test_equal_timestamp_uses_observed_order_and_late_records_do_not_replace_newer_evidence(self):
        evidence = VerificationEvidence()
        evidence.observe('Pruebas y validación', 'ok', stamp(20))
        evidence.observe('Edición de archivos', 'ok', stamp(20))
        self.assertTrue(evidence.summary()['edits_after_check'])
        evidence.observe('Compilación', 'ok', stamp(20))
        self.assertFalse(evidence.summary()['edits_after_check'])
        evidence.observe('Edición de archivos', 'ok', stamp(10))
        evidence.observe('Pruebas y validación', 'error', stamp(15))
        self.assertEqual(evidence.summary()['check_kind'], 'Compilación')
        self.assertEqual(evidence.summary()['check_outcome'], 'ok')
        self.assertFalse(evidence.summary()['edits_after_check'])

    def test_unknown_outcome_never_becomes_success_and_unrelated_activity_adds_no_evidence(self):
        evidence = VerificationEvidence()
        evidence.observe('Uso de herramientas', 'ok', stamp(10))
        self.assertEqual(verification_text(evidence.summary()), '')
        evidence.observe('Pruebas y validación', 'unsupported', stamp(11))
        self.assertIn('sin resultado conocido', verification_text(evidence.summary()))
        self.assertNotIn('éxito', verification_text(evidence.summary()))

    def test_evidence_survives_new_turn_and_short_action_list_eviction_without_retaining_commands(self):
        activity = Activity()
        def event(kind, at, turn='first', **payload):
            activity.observe({'type': 'event_msg', 'payload': {'type': kind, 'turn_id': turn, **payload}}, stamp(at))
        event('task_started', 1)
        event('item_completed', 10, item={'type': 'CommandExecution', 'id': 'check',
              'command': 'pytest PRIVATE_COMMAND', 'exit_code': 0, 'aggregated_output': 'PRIVATE_OUTPUT'})
        for at in range(11, 20):
            activity.add_action('Uso de herramientas', stamp(at), 'ok', str(at))
        event('task_complete', 20)
        event('task_started', 21, 'second')
        summary = activity.summary()
        self.assertEqual(summary['actions'], [])
        self.assertEqual(summary['verification']['check_at'], 10)
        text = details_text({'state': 'working', 'activity': summary}, 30)['verification']
        self.assertIn('hace 20 s', text)
        self.assertNotIn('PRIVATE', json.dumps(summary))
        self.assertNotIn('pytest', json.dumps(summary['verification']))

    def test_repeated_action_id_does_not_change_same_timestamp_order(self):
        activity = Activity()
        activity.add_action('Edición de archivos', stamp(10), 'ok', 'edit')
        activity.add_action('Pruebas y validación', stamp(10), 'ok', 'check')
        activity.add_action('Edición de archivos', stamp(10), 'ok', 'edit')
        self.assertFalse(activity.summary()['verification']['edits_after_check'])

    def test_many_events_retain_only_one_check_and_one_edit(self):
        evidence = VerificationEvidence()
        for at in range(1000):
            evidence.observe('Edición de archivos' if at % 2 else 'Pruebas y validación', 'ok', stamp(at + 1))
        self.assertLess(len(json.dumps(evidence.summary())), 200)
        self.assertEqual(evidence.summary()['check_at'], 999)
        self.assertEqual(evidence.summary()['edit_at'], 1000)


if __name__ == '__main__':
    unittest.main()
