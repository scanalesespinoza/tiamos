import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock
import wave

from agent_sounds import NOTES, SoundEvents, Sounds, chime


def chat(ident='a', complete=0, error=0, level=1, updated=0, phase='Analizando', failed=False):
    return {'id': ident, 'state': 'working', 'activity': {
        'last_completed_at': complete, 'last_completion_error': failed,
        'phase': phase, 'stats': {'level': level}, 'updated_at': updated,
        'actions': [{'at': error, 'outcome': 'error'}] if error else []}}


class SoundEventTests(unittest.TestCase):
    def test_startup_new_history_and_incremental_old_records_are_silent(self):
        events = SoundEvents()
        self.assertIsNone(events.observe([chat(complete=99, error=98)], 100))
        self.assertIsNone(events.observe([chat(complete=99, error=98), chat('old', complete=99)], 101))
        self.assertIsNone(events.observe([chat(complete=99.5, level=4, updated=99.5)], 102))
        self.assertEqual(events.observe([chat(complete=103, level=4, updated=103)], 104), 'complete')
        self.assertIsNone(events.observe([chat(complete=103, level=4, updated=103)], 105))

    def test_attention_requires_explicit_transition_not_tool_wait(self):
        events = SoundEvents()
        events.observe([chat()], 100)
        self.assertIsNone(events.observe([chat(phase='Esperando una herramienta')], 101))
        self.assertEqual(events.observe([chat(phase='Esperando intervención')], 102), 'attention')
        self.assertIsNone(events.observe([chat(phase='Esperando intervención')], 103))
        events.observe([chat()], 104)
        self.assertEqual(events.observe([chat(phase='Esperando intervención')], 105), 'attention')

    def test_errors_are_throttled_and_failed_completion_is_not_success(self):
        events = SoundEvents()
        events.observe([chat()], 100)
        self.assertEqual(events.observe([chat(error=101)], 101), 'error')
        self.assertIsNone(events.observe([chat(error=102)], 102))
        self.assertIsNone(events.observe([chat(error=102, complete=103, failed=True)], 103))
        self.assertEqual(events.observe([chat(error=122)], 122), 'error')
        self.assertIsNone(events.observe([chat(phase='Turno interrumpido')], 123))

    def test_batch_coalesces_by_priority_and_removed_sessions_leave_no_state(self):
        events = SoundEvents()
        events.observe([chat(), chat('b')], 100)
        self.assertEqual(events.observe([chat(complete=101, updated=101, level=2),
                                         chat('b', phase='Esperando intervención')], 101), 'attention')
        self.assertIsNone(events.observe([], 102))
        self.assertEqual(events.sessions, {})
        self.assertIsNone(events.observe([chat(complete=101)], 103))

    def test_live_level_gain_and_stale_completion(self):
        events = SoundEvents()
        events.observe([chat()], 100)
        self.assertEqual(events.observe([chat(level=2, updated=101)], 101), 'level')
        self.assertIsNone(events.observe([chat(level=2, complete=102, updated=102)], 170))

    def test_partial_reload_and_unmuting_do_not_replay_consumed_events(self):
        events = SoundEvents()
        events.observe([chat()], 100)
        # The observer keeps consuming events even when playback is muted.
        self.assertEqual(events.observe([chat(complete=101, updated=101, level=2)], 101), 'level')
        self.assertIsNone(events.observe([chat()], 102))
        self.assertIsNone(events.observe([chat(complete=101, updated=101, level=2)], 103))


class SoundPlaybackTests(unittest.TestCase):
    def test_volume_scales_valid_bounded_waveforms_without_clipping(self):
        for kind in NOTES:
            peaks = []
            for volume in (0, 25, 100):
                with wave.open(io.BytesIO(chime(kind, volume)), 'rb') as stream:
                    self.assertEqual((stream.getnchannels(), stream.getsampwidth(), stream.getframerate()), (1, 2, 22050))
                    self.assertLess(stream.getnframes() / 22050, .7)
                    data = stream.readframes(stream.getnframes())
                    peaks.append(max(abs(value) for value in struct.unpack('<' + 'h' * (len(data) // 2), data)))
            self.assertEqual(peaks[0], 0)
            self.assertAlmostEqual(peaks[1] / peaks[2], .25, places=3)
            self.assertLess(peaks[2], 8000)

    def test_settings_persist_mute_stops_and_zero_volume_never_plays(self):
        with tempfile.TemporaryDirectory() as directory:
            player = Mock()
            sounds = Sounds(directory, player=player)
            self.assertEqual(sounds.volume, 25)
            sounds.configure(volume=50, enabled=False)
            player.assert_called_with(None)
            self.assertFalse(sounds.play('complete', preview=True))
            restored = Sounds(directory, player=player)
            self.assertEqual((restored.enabled, restored.volume), (False, 50))
            sounds.configure(volume=0, enabled=True)
            player.reset_mock()
            self.assertFalse(sounds.play('complete'))
            player.assert_not_called()
            self.assertEqual(set(json.loads(sounds.path.read_text())), {'enabled', 'volume'})

    def test_async_backend_is_bounded_cached_and_has_no_replay_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            player, now = Mock(), [100]
            sounds = Sounds(directory, player=player, clock=lambda: now[0])
            self.assertTrue(sounds.play('complete'))
            path = player.call_args.args[0]
            first = path.read_bytes()
            self.assertFalse(sounds.play('error'))
            self.assertEqual(player.call_count, 1)
            now[0] = 104
            self.assertTrue(sounds.play('error'))
            sounds.configure(volume=50)
            self.assertTrue(sounds.play('complete', preview=True))
            self.assertNotEqual(first, path.read_bytes())
            self.assertEqual(len(list((Path(directory) / 'sounds').glob('*.wav'))), 2)

    def test_audio_failure_does_not_escape_and_invalid_settings_use_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'sounds.json').write_text('{"enabled":"false","volume":"loud"}')
            sounds = Sounds(directory, player=Mock(side_effect=RuntimeError('no device')))
            self.assertEqual((sounds.enabled, sounds.volume), (True, 25))
            self.assertFalse(sounds.play('complete'))
            self.assertIsNotNone(sounds.error)
            sounds.configure(enabled=False)
            self.assertFalse(sounds.enabled)


if __name__ == '__main__':
    unittest.main()
