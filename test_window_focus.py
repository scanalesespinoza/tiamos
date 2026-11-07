import unittest
from unittest.mock import Mock
from window_focus import avatar_size, dock_position, foreground_selection, WindowSnapshot


class FocusTests(unittest.TestCase):
    def test_native_window_observation_is_shared_only_for_current_tick(self):
        first, replacement = object(), object()
        inspect = Mock(side_effect=[first, None, replacement])
        tick = WindowSnapshot(inspect)
        for _ in range(10):
            self.assertIs(tick.inspect(123), first)
            self.assertIsNone(tick.inspect(456))
        self.assertEqual(inspect.call_count, 2)
        next_tick = WindowSnapshot(inspect)
        self.assertIs(next_tick.inspect(123), replacement)
        self.assertEqual(inspect.call_count, 3)

    def test_selection_exchanges_full_and_half_dimensions(self):
        self.assertEqual(avatar_size('a', 'a'), (178, 152))
        self.assertEqual(avatar_size('b', 'a'), (89, 76))
        self.assertEqual(avatar_size('a', 'b'), (89, 76))
        self.assertEqual(avatar_size('b', 'b'), (178, 152))
        self.assertEqual(avatar_size('a', None), (178, 152))
        self.assertEqual(avatar_size('b', None), (178, 152))

    def test_dock_is_inside_client_below_controls(self):
        for dpi in (96, 144, 192):
            client = (-1600, 100, -100, 1000)
            x, y = dock_position(client, dpi=dpi)
            self.assertGreaterEqual(x, client[0])
            self.assertLess(x + 178, client[2])
            self.assertGreaterEqual(y, client[1] + 48 * dpi / 96)
            self.assertLess(y + 152, client[3])
        self.assertIsNone(dock_position((0, 0, 100, 100)))

    def test_foreground_switch_and_shared_window_ambiguity(self):
        bindings = {'a': 123, 'b': 456}
        self.assertEqual(foreground_selection(bindings, 456, 'a'), 'b')
        self.assertEqual(foreground_selection(bindings, 123, 'b'), 'a')
        self.assertIsNone(foreground_selection(bindings, 789, 'a'))
        self.assertIsNone(foreground_selection({}, 123, 'a'))
        bindings['c'] = 123
        self.assertEqual(foreground_selection(bindings, 123, 'c'), 'c')
        self.assertIsNone(foreground_selection(bindings, 123, 'b'))

if __name__ == '__main__':
    unittest.main()
