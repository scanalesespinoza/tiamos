import os
import sys
import unittest
from unittest.mock import Mock

from attention_inbox import AttentionWindow


def row(kind='error', available=True):
    return dict(key=kind + ':a:10', id='a', kind=kind, at=10, session='Codex · Example',
                reason='Observed event', age='10s', available=available, stale=not available)


@unittest.skipUnless(sys.platform in ('win32', 'darwin') or os.environ.get('DISPLAY'), 'Native desktop display')
class AttentionWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.rows = [row()]
        self.open = Mock()
        self.ack = Mock(side_effect=lambda _: self.rows.clear())
        self.window = AttentionWindow(self.root, lambda: self.rows, self.open, self.ack)

    def tearDown(self):
        self.root.destroy()

    def test_lazy_window_open_acknowledgment_and_empty_state(self):
        self.window.refresh()
        self.assertIsNone(self.window.window)
        self.window.show()
        self.root.update_idletasks()
        self.assertEqual(len(self.window.tree.get_children()), 1)
        self.window.open_selected()
        self.open.assert_called_once_with('a')
        self.window.mark_seen()
        self.ack.assert_called_once()
        self.assertEqual(self.window.tree.get_children(), ())
        self.assertIn('No hay avisos', self.window.message.get())
        self.assertEqual(str(self.window.open_button['state']), 'disabled')

    def test_live_request_cannot_be_dismissed_and_stale_session_cannot_be_opened(self):
        self.rows[:] = [row('input')]
        self.window.show()
        self.assertEqual(str(self.window.seen_button['state']), 'disabled')
        self.window.mark_seen()
        self.ack.assert_not_called()
        self.rows[:] = [row(available=False)]
        self.window.refresh()
        self.window.open_selected()
        self.open.assert_not_called()
        self.window.mark_seen()
        self.ack.assert_called_once()

    def test_age_refresh_preserves_selection_and_hidden_window_does_no_work(self):
        self.rows[:] = [row('input'), row()]
        self.window.show()
        self.window.tree.selection_set('error:a:10')
        self.rows[0]['age'] = '11s'
        self.window.refresh()
        self.assertEqual(self.window.tree.selection(), ('error:a:10',))
        self.window.window.withdraw()
        self.window.get_rows = Mock(side_effect=AssertionError('Hidden window rendered'))
        self.window.refresh()

    def test_session_removed_between_refresh_and_click_is_not_opened(self):
        self.window.show()
        self.rows.clear()
        self.window.open_selected()
        self.open.assert_not_called()
        self.assertEqual(self.window.tree.selection(), ())


if __name__ == '__main__':
    unittest.main()
