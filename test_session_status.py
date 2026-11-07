import unittest

from agent_sounds import SoundEvents
from avatar_personality import visual_state
from group_menu import team_status
from session_attention import AttentionInbox
from session_details import compact_caption, details_text
from session_status import status_code, needs_input


def session(state='working', phase='Analizando', **extra):
    return dict(id='a', state=state, activity={'phase': phase, 'finished_at': 100}, **extra)


class SessionStatusTests(unittest.TestCase):
    def test_distinct_observed_states_have_matching_captions_and_sprites(self):
        cases = [
            (session(phase='Esperando intervención'), 'input', 'Necesita tu respuesta', 'attention'),
            (session(phase='Esperando una herramienta'), 'tool_wait', 'Esperando herramienta', 'waiting'),
            (session('sleeping', 'Turno interrumpido'), 'interrupted', 'Turno interrumpido', 'paused'),
            (session('sleeping', 'Turno finalizado'), 'completed', 'Turno terminado', 'sleeping'),
            (session('sleeping'), 'resting', 'En descanso', 'sleeping'),
            (session('unknown'), 'unknown', 'Sin estado disponible', 'unknown'),
            (session(unavailable=True), 'unavailable', 'Sin conexión', 'unknown'),
            (session(terminal={'live': False}), 'closed', 'CLI cerrado', 'sleeping'),
        ]
        for chat, code, caption, sprite in cases:
            with self.subTest(code=code):
                self.assertEqual(status_code(chat), code)
                self.assertEqual(compact_caption(chat), caption)
                self.assertIn(caption, details_text(chat, 110)['state'])
                self.assertEqual(visual_state(chat), sprite)
                self.assertEqual(needs_input(chat), code == 'input')

    def test_no_time_based_guess_and_no_finished_status_without_valid_evidence(self):
        chat = session(phase='Esperando una herramienta')
        chat['activity']['updated_at'] = 1
        self.assertEqual(status_code(chat), 'tool_wait')
        for finished in (None, 0, -1, True, float('nan'), '100'):
            for phase in ('Turno finalizado', 'Turno interrumpido'):
                chat = session('sleeping', phase)
                chat['activity']['finished_at'] = finished
                self.assertEqual(status_code(chat), 'resting')
        self.assertEqual(status_code({}), 'unknown')

    def test_closed_or_unavailable_session_does_not_ask_for_input(self):
        for extra in ({'unavailable': True}, {'terminal': {'live': False}}):
            chat = session(phase='Esperando intervención', **extra)
            inbox = AttentionInbox()
            inbox.observe([chat], 110)
            self.assertEqual(inbox.rows({'a': {'chat': chat}}, {}, 110), [])
            counts = team_status({'a': {'chat': chat}})
            self.assertEqual(counts['attention'], 0)
            self.assertEqual(counts['working'], 0)

    def test_unavailable_input_does_not_replay_a_sound_on_recovery(self):
        events = SoundEvents()
        events.observe([session()], 100)
        asking = session(phase='Esperando intervención')
        self.assertEqual(events.observe([asking], 101), 'attention')
        self.assertIsNone(events.observe([dict(asking, unavailable=True)], 102))
        self.assertIsNone(events.observe([asking], 103))
        self.assertEqual(visual_state(asking, unavailable=True), 'unknown')

    def test_current_input_takes_precedence_over_a_previous_tool_error(self):
        chat = session(phase='Esperando intervención')
        chat['activity']['actions'] = [{'outcome': 'error', 'at': 90}]
        self.assertEqual(visual_state(chat), 'attention')
        self.assertEqual(compact_caption(chat, False), 'Tu respuesta')

    def test_missing_state_keeps_prior_input_stale_and_cannot_open_it(self):
        inbox = AttentionInbox()
        inbox.observe([session(phase='Esperando intervención')], 100)
        unknown = session()
        del unknown['state']
        inbox.observe([unknown], 101)
        row = inbox.rows({'a': {'chat': unknown}}, {}, 102)[0]
        self.assertTrue(row['stale'])
        self.assertFalse(row['available'])

    def test_error_sound_uses_observed_watermark_after_short_action_history_rolls_over(self):
        events = SoundEvents()
        events.observe([session()], 100)
        current = session()
        current['activity'].update(last_error_at=101, actions=[{'at': 102, 'outcome': 'ok'}])
        self.assertEqual(events.observe([current], 103), 'error')
        self.assertIsNone(events.observe([current], 104))


if __name__ == '__main__':
    unittest.main()
