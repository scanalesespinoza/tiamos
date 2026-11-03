import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from codex_float import Trace
from session_activity import Activity, category, is_control_request, safe_preview
from session_details import card_position, compact_caption, details_text


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.activity = Activity()
        self.now = dt.datetime(2026, 11, 3, 6, tzinfo=dt.timezone.utc)

    def observe(self, event, **payload):
        self.activity.observe({'type': 'event_msg', 'payload': {'type': event, **payload}}, self.now)

    def test_objective_survives_continuation_and_instruction_context(self):
        self.observe('user_message', message='Improve the floating companions')
        self.observe('task_started', turn_id='a')
        for control in ['loop and continue for 1 hour', 'continúa', '# AGENTS.md instructions', '<environment_context>']:
            self.assertTrue(is_control_request(control))
            self.observe('user_message', message=control)
        self.assertEqual(self.activity.objective, 'Improve the floating companions')
        self.observe('user_message', message='Now improve the error messages')
        self.assertEqual(self.activity.objective, 'Now improve the error messages')

    def test_completed_actions_are_bounded_deduplicated_and_keep_outcomes(self):
        self.observe('task_started', turn_id='a')
        for index in range(8):
            item = {'type': 'CommandExecution', 'id': str(index), 'command': 'python -m unittest',
                'aggregated_output': 'PRIVATE OUTPUT', 'exit_code': index % 2}
            self.observe('item_completed', item=item)
            self.observe('item_completed', item=item)
        summary = self.activity.summary()
        self.assertEqual(summary['action_count'], 8)
        self.assertEqual(len(summary['actions']), 4)
        self.assertEqual(summary['actions'][0]['outcome'], 'error')
        self.assertEqual(summary['actions'][1]['outcome'], 'ok')
        self.assertNotIn('PRIVATE', json.dumps(summary))
        self.assertNotIn('unittest', json.dumps(summary))

    def test_reasoning_content_and_tool_output_are_never_exposed(self):
        for kind, payload in [('reasoning', {'summary': 'PRIVATE REASONING', 'encrypted_content': 'PRIVATE'}),
            ('function_call', {'name': 'exec_command', 'arguments': json.dumps({'cmd': 'git status -- PRIVATE_ARGUMENT'})})]:
            self.activity.observe({'type': 'response_item', 'payload': {'type': kind, **payload}}, self.now)
        self.observe('item_completed', item={'type': 'Reasoning', 'summary_text': 'PRIVATE'})
        self.assertNotIn('PRIVATE', json.dumps(self.activity.summary()))
        self.assertEqual(self.activity.phase, 'Revisión de cambios')

    def test_completion_only_finishes_matching_turn_and_new_turn_resets_progress(self):
        self.observe('task_started', turn_id='a')
        self.observe('item_completed', item={'type': 'AgentMessage', 'phase': 'commentary',
            'content': [{'type': 'Text', 'text': 'Running the validation'}]})
        self.observe('task_complete', turn_id='other')
        self.assertIsNone(self.activity.finished_at)
        self.observe('task_complete', turn_id='a')
        self.assertEqual(self.activity.phase, 'Turno finalizado')
        self.observe('task_started', turn_id='b')
        self.assertFalse(self.activity.progress)
        self.assertIsNone(self.activity.finished_at)

    def test_prose_redacts_credentials_paths_urls_and_identifiers(self):
        for prose in ['Use password=EXAMPLE', 'login -p EXAMPLE', 'Authorization: EXAMPLE', 'sk-EXAMPLEKEY']:
            self.assertNotIn('EXAMPLE', safe_preview(prose))
        cleaned = safe_preview('Read "D:\\private folder\\file.txt" and https://example.invalid/a?key=x by user@example.invalid')
        for private in ['private folder', 'example.invalid', 'user@']:
            self.assertNotIn(private, cleaned)
        self.assertLessEqual(len(safe_preview('a ' * 300)), 180)
        self.assertNotIn('\u202e', safe_preview('example\u202etext'))

    def test_code_blocks_and_inline_commands_are_omitted_from_prose(self):
        preview = safe_preview('Validate the change with `python private_script.py`.\n```powershell\nPRIVATE COMMAND\n```\nThen review the result.')
        self.assertNotIn('private_script', preview)
        self.assertNotIn('PRIVATE COMMAND', preview)
        self.assertIn('Validate the change', preview)
        self.assertIn('Then review the result', preview)
        self.assertNotIn('PRIVATE', safe_preview('Before ```bash\nPRIVATE unfinished block'))

    def test_loop_feature_requests_are_not_mistaken_for_continuation(self):
        self.assertFalse(is_control_request('Loop animations should stay smooth'))
        self.assertFalse(is_control_request('Continue improving the messages'))
        self.assertTrue(is_control_request('/loop 30s check status'))
        self.assertTrue(is_control_request('$adev'))

    def test_latest_error_is_contextual_and_clears_after_a_success(self):
        chat = {'state': 'working', 'activity': {'actions': [{'label': 'Pruebas y validación',
            'at': 100, 'outcome': 'error'}]}}
        detail = details_text(chat, 110)
        self.assertIn('error', detail['alert'])
        self.assertIn('sigue trabajando', detail['alert'])
        chat['activity']['actions'].insert(0, {'label': 'Edición de archivos', 'at': 105, 'outcome': 'ok'})
        detail = details_text(chat, 110)
        self.assertFalse(detail['alert'])
        self.assertIn('! Pruebas', detail['actions'])

    def test_trace_partial_record_and_truncation_reset_activity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rollout.jsonl'
            record = json.dumps({'type': 'event_msg', 'timestamp': self.now.isoformat(),
                'payload': {'type': 'user_message', 'message': 'A meaningful objective'}}) + '\n'
            path.write_text(record[:-5], encoding='utf-8')
            trace = Trace(path)
            trace.read()
            self.assertEqual(trace.activity.objective, '')
            with path.open('a', encoding='utf-8') as stream:
                stream.write(record[-5:])
            trace.read()
            self.assertEqual(trace.activity.objective, 'A meaningful objective')
            path.write_text('{}\n', encoding='utf-8')
            trace.read()
            self.assertEqual(trace.activity.objective, '')

    def test_fixed_categories_and_truthful_idle_duration(self):
        self.assertEqual(category('npm run test'), 'Pruebas y validación')
        self.assertEqual(category('git push'), 'Publicación y revisión')
        self.assertEqual(category(tool='apply_patch'), 'Edición de archivos')
        chat = {'state': 'sleeping', 'activity': {'started_at': 100, 'finished_at': 170,
            'updated_at': 170, 'phase': 'Turno finalizado', 'final': 'Validation passed'}}
        detail = details_text(chat, 500)
        self.assertIn('1 min 10 s', detail['activity'])
        self.assertIn('hace 5 min 30 s', detail['activity'])
        self.assertEqual(detail['report'], 'Validation passed')
        self.assertEqual(compact_caption(chat), 'En descanso')
        chat['state'] = 'working'
        chat['activity']['phase'] = 'Pruebas y validación'
        self.assertEqual(compact_caption(chat), 'Validando')

    def test_card_position_below_above_and_negative_monitor_coordinates(self):
        self.assertEqual(card_position((900, 10, 178, 152), (382, 400), (0, 0, 1920, 1080)), (798, 172))
        self.assertEqual(card_position((1800, 900, 89, 76), (382, 400), (0, 0, 1920, 1080)), (1538, 490))
        x, y = card_position((-1900, 0, 178, 152), (382, 400), (-1920, 0, 0, 1080))
        self.assertGreaterEqual(x, -1920)
        self.assertGreaterEqual(y, 0)


if __name__ == '__main__':
    unittest.main()
