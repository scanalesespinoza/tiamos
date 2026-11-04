import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

from avatar_layout import arrange, place_companion
from avatar_starred import (SYMBOLS, StarredMarker, StarredMenu, avatar_origin,
                            footprint, marker_rect, occupied_rect, preferences)


def overlaps(a, b):
    x, y, w, h = a
    ox, oy, ow, oh = b
    return x < ox + ow and x + w > ox and y < oy + oh and y + h > oy


class StarredLayoutTests(unittest.TestCase):
    def test_markers_face_inward_at_both_sizes_and_negative_monitor_coordinates(self):
        for width, height in ((178, 152), (89, 76)):
            avatar = (-900, 50, width, height)
            for anchor in ('top', 'left', 'right'):
                x, y, w, h = marker_rect(avatar, anchor)
                self.assertFalse(overlaps(avatar, (x, y, w, h)))
                if anchor == 'top':
                    self.assertGreater(y, avatar[1] + height)
                    self.assertLessEqual(abs((x + w / 2) - (avatar[0] + width / 2)), .5)
                elif anchor == 'right':
                    self.assertLess(x + w, avatar[0])
                else:
                    self.assertGreater(x, avatar[0] + width)

    def test_wrapped_mixed_sizes_reserve_space_for_markers(self):
        area = (-900, 40, 0, 800)
        sizes = {str(i): (178, 152) if i % 2 else (89, 76) for i in range(9)}
        for anchor in ('top', 'left', 'right'):
            packed = arrange([(key, *footprint(size, anchor, True)) for key, size in sizes.items()], area, anchor)
            rectangles = []
            for key, point in packed.items():
                size = sizes[key]
                x, y = avatar_origin(*point, size, anchor, True)
                avatar = (x, y, *size)
                rectangles.extend((avatar, marker_rect(avatar, anchor)))
                self.assertEqual(occupied_rect(avatar, anchor, True), (*point, *footprint(size, anchor, True)))
            for index, rect in enumerate(rectangles):
                x, y, w, h = rect
                self.assertTrue(area[0] <= x and area[1] <= y and x + w <= area[2] and y + h <= area[3])
                self.assertTrue(all(not overlaps(rect, other) for other in rectangles[index + 1:]))

    def test_unmarked_avatars_keep_original_footprint(self):
        for anchor in ('top', 'right', 'left'):
            self.assertEqual(footprint((89, 76), anchor, False), (89, 76))
            self.assertEqual(avatar_origin(30, 40, (89, 76), anchor, False), (30, 40))

    def test_invalid_preferences_are_ignored_and_unknown_symbol_defaults_to_star(self):
        self.assertEqual(preferences([]), {})
        values = preferences({'one': {'enabled': True}, 'two': {'enabled': True, 'symbol': 'new'},
                              'bad': [], 'invalid': {'symbol': []}, 'truthy': {'enabled': 'yes'}})
        self.assertEqual(values['one'], {'enabled': True, 'symbol': 'star'})
        self.assertEqual(values['two']['symbol'], 'star')
        self.assertFalse(values['truthy']['enabled'])
        self.assertNotIn('bad', values)
        self.assertNotIn('invalid', values)


@unittest.skipUnless(sys.platform in ('win32', 'darwin') or os.environ.get('DISPLAY'), 'Native desktop display')
class StarredWidgetTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_menu_default_select_disable_and_reload_keep_symbol(self):
        from codex_float import atomic_json
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'starred.json'
            menu = StarredMenu(self.root, {}, lambda record: atomic_json(path, {'session': record}))
            menu.menu.invoke(0)
            self.assertEqual(json.loads(path.read_text())['session'], {'enabled': True, 'symbol': 'star'})
            menu.menu.invoke(4)  # Diamond; selecting a symbol also enables the marker.
            menu.menu.invoke(0)
            record = preferences(json.loads(path.read_text()))['session']
            self.assertEqual(record, {'enabled': False, 'symbol': 'diamond'})
            restored = StarredMenu(self.root, record, Mock())
            restored.menu.invoke(0)
            restored.on_change.assert_called_once_with({'enabled': True, 'symbol': 'diamond'})
            restored.menu.invoke(0)
            restored.menu.invoke(3)  # Circle re-enables a disabled marker.
            self.assertTrue(restored.enabled.get())

    def test_marker_tracks_layout_size_hide_and_destroy_without_duplicate_canvas_items(self):
        marker = StarredMarker(self.root, Mock(), Mock())
        marker.sync((100, 100, 178, 152), 'right', None)
        self.assertIsNone(marker.window)
        for anchor, size in [('right', (178, 152)), ('top', (89, 76)), ('left', (178, 152))]:
            rect = (100, 100, *size)
            marker.sync(rect, anchor, 'star')
            self.root.update()
            x, y, extent, _ = marker_rect(rect, anchor)
            self.assertEqual(marker.status(), {'visible': True, 'position': [x, y], 'size': extent})
            items = marker.canvas.find_all()
            marker.sync(rect, anchor, 'star')
            self.assertEqual(marker.canvas.find_all(), items)
            for symbol, _ in SYMBOLS:
                marker.sync(rect, anchor, symbol)
                self.assertEqual(len(marker.canvas.find_all()), 1)
        marker.sync(rect, 'left', 'star', visible=False)
        self.assertFalse(marker.status()['visible'])
        marker.sync(rect, 'left', 'star')
        self.root.update()
        self.assertTrue(marker.status()['visible'])
        window = marker.window
        marker.sync(rect, 'left', None)
        self.assertFalse(window.winfo_exists())
        self.assertIsNone(marker.window)
        marker.destroy()  # Safe when a session disappears after being unstarred.

    def test_markers_share_requested_geometry_before_tk_commits_first_placement_and_move(self):
        import tkinter as tk
        avatar = tk.Toplevel(self.root)
        avatar.withdraw()
        avatar.overrideredirect(True)
        marker = StarredMarker(self.root, Mock(), Mock())
        entry = {'window': avatar}
        for x, y, width, height in [(300, 200, 178, 152), (400, 100, 89, 76)]:
            entry['size'] = (width, height)
            place_companion(entry, x, y)
            avatar.deiconify()
            marker.sync((*entry['position'], *entry['size']), 'top', 'star')
            self.root.update()
            self.assertEqual((avatar.winfo_x(), avatar.winfo_y()), (x, y))
            self.assertEqual(marker.status()['position'],
                             list(marker_rect((x, y, width, height), 'top')[:2]))
