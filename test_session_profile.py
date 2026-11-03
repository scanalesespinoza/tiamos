"""Exercise the actual compact card widgets without activating desktop windows."""
import datetime as dt
import sys
import unittest
from unittest.mock import Mock, patch

from session_details import DetailsCard
from session_metrics import SessionMetrics


@unittest.skipUnless(sys.platform == 'win32', 'Windows Tk card')
class ProfileCardTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.tk.call('tk', 'scaling', 96 / 72)
        self.owner = tk.Toplevel(self.root)
        self.owner.withdraw()
        self.owner.geometry('178x152+100+100')
        metrics = SessionMetrics()
        now = dt.datetime.now().astimezone()
        metrics.start(now, 'turn')
        metrics.action('Pruebas y validación', 'ok', now)
        metrics.finish(now + dt.timedelta(seconds=60), True)
        self.entries = {'session': {'window': self.owner, 'size': (178, 152),
            'chat': {'title': 'Example session', 'provider': 'codex', 'state': 'sleeping',
                     'activity': {'stats': metrics.summary(), 'objective': 'Example objective'}}}}
        self.viewed = Mock()
        with patch.object(DetailsCard, 'no_activate'):
            self.card = DetailsCard(self.root, self.entries, Mock(), self.viewed)
        self.card.ident = 'session'

    def tearDown(self):
        self.root.destroy()

    def test_profile_replaces_activity_in_same_compact_window(self):
        self.card.refresh()
        self.assertEqual(self.card.labels['objective'].winfo_manager(), 'grid')
        self.assertEqual(self.card.labels['profile_today'].winfo_manager(), '')
        self.card.toggle_profile()
        self.root.update_idletasks()
        self.assertEqual(self.card.labels['objective'].winfo_manager(), '')
        self.assertEqual(self.card.labels['profile_today'].winfo_manager(), 'grid')
        self.assertIn('Nivel 1', self.card.labels['profile_level'].cget('text'))
        self.assertEqual(self.card.profile_button.cget('text'), 'Actividad')
        self.assertLess(self.card.window.winfo_reqheight(), 550)
        self.assertEqual(self.entries['session']['size'], (178, 152))
        self.card.toggle_profile()
        self.assertEqual(self.card.labels['objective'].winfo_manager(), 'grid')
        self.assertEqual(self.card.labels['profile_today'].winfo_manager(), '')

    def test_profile_only_does_not_acknowledge_an_unread_result(self):
        with patch.object(self.card, 'no_activate'), patch.object(self.card.window, 'deiconify'), \
             patch.object(self.card.window, 'lift'):
            self.card.show('session', pinned=True, profile=True)
            self.viewed.assert_not_called()
            self.card.show('session', pinned=True)
            self.viewed.assert_called_once_with('session')

    def test_unavailable_statistics_are_explicitly_stale(self):
        self.entries['session']['unavailable'] = True
        self.card.profile = True
        self.card.refresh()
        self.assertIn('última lectura', self.card.labels['profile_note'].cget('text'))


if __name__ == '__main__':
    unittest.main()
