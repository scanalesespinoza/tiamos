import sys
import unittest
from unittest.mock import Mock

from group_menu import GroupMenu, HistoryPicker


@unittest.skipUnless(sys.platform == 'win32', 'Windows native controls')
class GroupMenuTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_visibility_labels_and_individual_controls_remain_accessible(self):
        hidden = [False]
        excluded = set()
        entries = {'a': {'chat_title': 'Example', 'chat': {'provider': 'claude'}}}
        details = Mock()
        def toggle(): hidden[0] = not hidden[0]
        def toggle_one(key): excluded.add(key) if key not in excluded else excluded.remove(key)
        menu = GroupMenu(self.root, details, entries, lambda: hidden[0], lambda: excluded,
                         toggle, toggle_one, Mock(), Mock())
        event = Mock(x_root=100, y_root=100)
        menu.popup(event)
        self.assertEqual(menu.menu.entrycget(0, 'label'), 'Ocultar avatares')
        menu.menu.invoke(0)
        menu.popup(event)
        self.assertEqual(menu.menu.entrycget(0, 'label'), 'Mostrar avatares')
        self.assertEqual(menu.window.winfo_exists(), 1)
        menu.avatar_menu.invoke(0)
        self.assertEqual(excluded, {'a'})
        menu.popup(event)
        self.assertFalse(menu.variables[0].get())
        menu.menu.invoke(0)
        self.assertFalse(hidden[0])
        self.assertEqual(excluded, {'a'})
        self.assertEqual(details.popup_menu.call_count, 3)

    def test_history_filter_excludes_existing_and_show_requires_explicit_selection(self):
        selected = Mock()
        picker = HistoryPicker(self.root, Mock(), selected, lambda: {'current'})
        record = {'id': 'old', 'provider': 'claude', 'title': 'Build verification', 'updated_at': 100}
        picker.results.put(([record, dict(record, id='current')], []))
        picker.poll()
        self.assertEqual(picker.tree.get_children(), ('old',))
        selected.assert_not_called()
        picker.query.set('codex')
        self.assertFalse(picker.tree.get_children())
        picker.query.set('verification')
        picker.tree.selection_set('old')
        picker.choose()
        selected.assert_called_once_with(record)
        self.assertEqual(picker.window.state(), 'withdrawn')


if __name__ == '__main__':
    unittest.main()
