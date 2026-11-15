import unittest
from avatar_layout import cycle_position, arrange, register_available, menu_after


class LayoutTests(unittest.TestCase):
    def test_group_control_packs_last_and_survives_an_empty_group(self):
        for anchor in ('top', 'right', 'left', 'bottom'):
            packed = arrange([('a', 178, 152), ('menu', 36, 36)], (0, 0, 800, 600), anchor)
            axis = 0 if anchor in ('top', 'bottom') else 1
            self.assertGreater(packed['menu'][axis], packed['a'][axis])
            self.assertIn('menu', arrange([('menu', 36, 36)], (0, 0, 800, 600), anchor))

    def test_control_follows_manual_avatars_without_covering_them(self):
        rectangles = [(300, 200, 178, 152), (600, 500, 178, 76)]
        for anchor in ('top', 'left', 'right', 'bottom'):
            x, y = menu_after(rectangles, (0, 0, 800, 600), anchor)
            self.assertTrue(0 <= x <= 764 and 0 <= y <= 564)
            self.assertTrue(all(not (x < ox + w and x + 36 > ox and y < oy + h and y + 36 > oy)
                                for ox, oy, w, h in rectangles))

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
        for mode in ('top', 'left', 'right', 'bottom'):
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

    def test_page_cycle_wraps_both_directions(self):
        current = 'top'
        for direction, sequence in ((1, ('left', 'bottom', 'right', 'top')), (-1, ('right', 'bottom', 'left', 'top'))):
            for expected in sequence:
                current = cycle_position(current, direction)
                self.assertEqual(current, expected)

    def test_bottom_aligns_mixed_sizes_and_wraps_upward_on_offset_monitor(self):
        area = (-1000, 40, 0, 900)
        items = [('a', 178, 152), ('b', 89, 76), ('menu', 36, 36)]
        positions = arrange(items, area, 'bottom')
        for ident, width, height in items:
            self.assertEqual(positions[ident][1] + height, 888)
        self.assertLessEqual(abs(positions['a'][0] + positions['menu'][0] + 36 + 1000), 1)
        wrapped = arrange([('a', 178, 152), ('b', 178, 152)], (-300, 40, 0, 900), 'bottom')
        self.assertLess(wrapped['b'][1] + 152, wrapped['a'][1])

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
