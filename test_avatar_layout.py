import unittest
from avatar_layout import arrange, register_available


class LayoutTests(unittest.TestCase):
    def test_top_center_adapts_to_actual_avatar_sizes(self):
        items = [('a', 178, 152), ('b', 89, 76), ('c', 89, 76)]
        result = arrange(items, (0, 0, 1920, 1080))
        self.assertEqual(result['a'][1], 12)
        self.assertEqual(result['a'][0] + 178 + 12, result['b'][0])
        self.assertEqual(result['b'][0] + 89 + 12, result['c'][0])
        self.assertEqual(result['a'][0] + result['c'][0] + 89, 1920)

    def test_side_groups_are_vertically_centered(self):
        items = [('a', 178, 152), ('b', 89, 76)]
        for mode in ('left', 'right'):
            result = arrange(items, (-1920, 0, 0, 1080), mode)
            self.assertEqual(result['a'][1] + result['b'][1] + 76, 1080)
            for ident, width, _ in items:
                self.assertEqual(result[ident][0] if mode == 'left' else result[ident][0] + width, -1908 if mode == 'left' else -12)

    def test_wrapping_stays_inside_work_area_without_overlap(self):
        items = [(str(i), 178, 152) for i in range(10)]
        for mode in ('top', 'left', 'right'):
            area = (0, 40, 1440, 940)
            result = arrange(items, area, mode)
            rectangles = [(x, y, x + 178, y + 152) for x, y in result.values()]
            for index, (left, top, right, bottom) in enumerate(rectangles):
                self.assertGreaterEqual(left, area[0])
                self.assertGreaterEqual(top, area[1])
                self.assertLessEqual(right, area[2])
                self.assertLessEqual(bottom, area[3])
                for other in rectangles[index + 1:]:
                    self.assertFalse(left < other[2] and right > other[0] and top < other[3] and bottom > other[1])

    def test_busy_hotkey_group_is_released_before_fallback(self):
        released = []
        def register(ident, modifiers, key):
            return not (modifiers == 0x4003 and key == 0x27)
        held, labels = register_available(register, released.append)
        self.assertEqual(released, [0x7a10])
        self.assertEqual(len(held), 4)
        self.assertTrue(all(label.startswith('Ctrl+Alt+Shift+') for label in labels.values()))

    def test_down_toggle_registers_without_key_repeat_and_releases_collisions(self):
        calls, released = [], []
        def register(ident, modifiers, key):
            calls.append((ident, modifiers, key))
            return not (modifiers == 0x4003 and key == 0x28)
        held, labels = register_available(register, released.append)
        self.assertEqual(released, [0x7a10, 0x7a11, 0x7a12])
        self.assertEqual(len(held), 4)
        self.assertEqual(labels['toggle_visibility'], 'Ctrl+Alt+Shift+Down')
        self.assertTrue(all(modifiers & 0x4000 for _, modifiers, _ in calls))

    def test_preferred_group_includes_down_visibility_toggle(self):
        held, labels = register_available(lambda *_: True, lambda _: None)
        self.assertEqual(len(held), 4)
        self.assertEqual(labels['toggle_visibility'], 'Ctrl+Alt+Down')


if __name__ == '__main__':
    unittest.main()
