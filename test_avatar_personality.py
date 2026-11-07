import copy
import datetime as dt
import unittest
from PIL import Image, ImageChops, ImageColor

from avatar_personality import COLORS, STATES, Notices, customize, identity, render_frames, visual_state
from session_activity import Activity


def chat(finished=None, phase='Turno finalizado', outcome='ok', state='sleeping'):
    return {'id': 'session', 'state': state, 'activity': {'finished_at': finished,
        'phase': phase, 'actions': [{'outcome': outcome}]}}


class PersonalityTests(unittest.TestCase):
    def test_identities_survive_restart_and_avoid_collisions_until_palette_is_full(self):
        registry = {}
        assigned = [identity(str(n), registry) for n in range(32)]
        self.assertEqual(len(set(assigned)), 32)
        restored = dict(registry)
        self.assertEqual([identity(str(n), restored) for n in reversed(range(32))], list(reversed(assigned)))
        color, accessory = identity('overflow', restored)
        self.assertIn(color, COLORS)
        self.assertIn(accessory, range(4))

    def test_notices_are_persistent_but_historical_results_never_celebrate(self):
        notices = Notices()
        self.assertEqual(notices.observe([chat(100)], 101), (True, set()))
        self.assertTrue(notices.pending('session'))
        self.assertEqual(notices.observe([chat(100)], 102), (False, set()))
        restored = Notices(copy.deepcopy(notices.records))
        self.assertTrue(restored.pending('session'))
        self.assertTrue(restored.acknowledge('session'))
        self.assertFalse(restored.acknowledge('session'))
        self.assertFalse(Notices(copy.deepcopy(restored.records)).pending('session'))
        self.assertFalse(restored.pending('unknown'))

    def test_customization_preserves_other_choice_survives_reload_and_resets_without_collision(self):
        registry = {}
        original_color, original_accessory = identity('session', registry)
        self.assertEqual(customize('session', registry, color=2), (COLORS[2], original_accessory))
        self.assertEqual(customize('session', registry, accessory=3), (COLORS[2], 3))
        self.assertEqual(identity('session', dict(registry)), (COLORS[2], 3))
        original_slot = original_accessory * len(COLORS) + COLORS.index(original_color)
        registry['other'] = original_slot
        reset = customize('session', registry, reset=True)
        self.assertNotEqual(reset, identity('other', registry))
        self.assertEqual(registry['other'], original_slot)
        before = dict(registry)
        with self.assertRaises(ValueError):
            customize('session', registry, color=99)
        self.assertEqual(registry, before)

    def test_new_result_celebrates_once_and_later_work_preserves_unread_result(self):
        notices = Notices()
        notices.observe([chat(state='working')], 99)
        self.assertEqual(notices.observe([chat(100)], 101), (True, {'session'}))
        self.assertEqual(notices.observe([chat(100)], 102), (False, set()))
        notices.observe([chat(state='working')], 103)
        self.assertTrue(notices.pending('session'))
        notices.acknowledge('session')
        self.assertEqual(notices.observe([chat(110)], 111), (True, {'session'}))
        self.assertTrue(notices.pending('session'))

    def test_interrupted_turn_has_no_result_and_error_or_old_completion_does_not_celebrate(self):
        notices = Notices()
        notices.observe([], 90)
        self.assertEqual(notices.observe([chat(100, phase='Turno interrumpido')], 101), (False, set()))
        self.assertFalse(notices.pending('session'))
        self.assertEqual(notices.observe([chat(110, outcome='error')], 111), (True, set()))
        self.assertTrue(notices.pending('session'))
        self.assertEqual(notices.observe([chat(120)], 200), (True, set()))

    def test_completion_between_polls_is_retained_when_next_turn_has_already_started(self):
        activity = Activity()
        def event(kind, stamp, turn):
            activity.observe({'type': 'event_msg', 'payload': {'type': kind, 'turn_id': turn}},
                dt.datetime.fromtimestamp(stamp, dt.timezone.utc))
        notices = Notices()
        notices.observe([], 90)
        event('task_started', 99, 'first')
        event('task_complete', 100, 'first')
        event('task_started', 101, 'second')
        self.assertIsNone(activity.finished_at)
        current = {'id': 'session', 'state': 'working', 'activity': activity.summary()}
        self.assertEqual(notices.observe([current], 102), (True, set()))
        self.assertTrue(notices.pending('session'))
        notices.acknowledge('session')
        event('turn_aborted', 103, 'second')
        current['activity'] = activity.summary()
        self.assertEqual(notices.observe([current], 104), (False, set()))
        self.assertFalse(notices.pending('session'))

    def test_activity_gestures_do_not_change_lifecycle_or_claim_success(self):
        for phase, expected in [('Exploración de archivos', 'reading'), ('Inspección visual', 'reading'),
            ('Revisión de cambios', 'reading'), ('Investigación', 'reading'),
            ('Edición de archivos', 'editing'), ('Pruebas y validación', 'testing'),
            ('Compilación', 'testing'), ('Esperando una herramienta', 'waiting'), ('Analizando', 'working')]:
            with self.subTest(phase=phase):
                self.assertEqual(visual_state(chat(phase=phase, state='working')), expected)
        self.assertEqual(visual_state(chat(outcome='error', state='working'), greeting=True), 'error')
        self.assertEqual(visual_state(chat(), celebrating=True), 'celebrating')
        self.assertEqual(visual_state(chat(), greeting=True), 'greeting')
        self.assertEqual(visual_state(chat(), carried=True), 'carried')
        self.assertEqual(visual_state(chat()), 'sleeping')

    def test_all_gestures_render_at_both_sizes_for_each_accessory(self):
        for accessory in range(4):
            for state in STATES:
                with self.subTest(state=state, accessory=accessory):
                    frames = render_frames(state, COLORS[accessory], accessory)
                    self.assertEqual(len(frames), 8)
                    self.assertTrue(all(frame.size == (160, 104) for frame in frames))
                    self.assertEqual(frames[0].resize((80, 52)).size, (80, 52))
                    self.assertGreater(len(frames[0].getcolors(maxcolors=160 * 104)), 2)

    def test_custom_backgrounds_remain_opaque_and_seamless_at_both_sizes(self):
        for background in ('#24364b', '#493326', '#ffffff', '#000000'):
            for state in STATES:
                with self.subTest(background=background, state=state):
                    for frame in render_frames(state, COLORS[0], background=background):
                        self.assertEqual(frame.mode, 'RGB')
                        for image in (frame, frame.resize((80, 52), Image.Resampling.LANCZOS)):
                            for corner in ((0, 0), (image.width - 1, image.height - 1)):
                                self.assertEqual(image.getpixel(corner), ImageColor.getrgb(background))

    def test_accessories_stay_distinct_with_the_same_color_at_half_size(self):
        for state in STATES:
            silhouettes = [render_frames(state, COLORS[0], accessory)[0]
                           .resize((80, 52), Image.Resampling.LANCZOS).tobytes()
                           for accessory in range(4)]
            self.assertEqual(len(set(silhouettes)), 4, state)

    def test_blink_does_not_hide_the_face_used_by_quiet_mode(self):
        for state in ('working', 'editing', 'reading', 'greeting'):
            frames = render_frames(state, COLORS[0])
            # The app freezes on frame zero in quiet mode. The blink belongs
            # to the animated sequence, while the quiet face keeps open eyes.
            open_face = frames[0].crop((54, 35, 108, 51))
            blink_face = frames[6].crop((54, 35, 108, 51))
            self.assertIsNotNone(ImageChops.difference(open_face, blink_face).getbbox())


if __name__ == '__main__':
    unittest.main()
