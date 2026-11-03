import unittest
import sys
from terminal_discovery import match_session, TabBridge


class TerminalMatchingTests(unittest.TestCase):
    def test_resumed_desktop_thread_matches_cli_footer(self):
        threads = [{'id': 'resumed', 'cwd': 'D:\\work', 'name': 'Fix build', 'title': 'old question'}]
        self.assertEqual(match_session({'workspace': 'd:\\work', 'title': 'Fix build'}, threads, {'d:\\work'}), 'resumed')

    def test_distinct_threads_in_same_workspace_use_exact_names(self):
        threads = [{'id': 'a', 'cwd': 'D:\\work', 'name': 'First'}, {'id': 'b', 'cwd': 'D:\\work', 'name': 'Second'}]
        self.assertEqual(match_session({'workspace': 'D:\\work', 'title': 'Second'}, threads, {'d:\\work'}), 'b')
        self.assertIsNone(match_session({'workspace': 'D:\\work', 'title': 'Unknown'}, threads, {'d:\\work'}))

    def test_stale_title_uses_only_unique_recent_workspace(self):
        threads = [{'id': 'old', 'cwd': 'D:\\work', 'name': 'Older', 'recent': False}, {'id': 'current', 'cwd': 'D:\\work', 'name': 'Renamed', 'recent': True}]
        self.assertEqual(match_session({'workspace': 'D:\\work', 'title': 'Cached title'}, threads, {'d:\\work'}), 'current')
        self.assertIsNone(match_session({'workspace': 'D:\\work', 'title': 'Unknown new session'}, threads, {'d:\\work': 2}))

    def test_footer_without_a_live_cli_is_not_a_session(self):
        threads = [{'id': 'a', 'cwd': 'D:\\work', 'name': 'First'}]
        self.assertIsNone(match_session({'workspace': 'D:\\work', 'title': 'First'}, threads, set()))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows UI Automation transport')
    def test_metadata_bridge_handles_empty_window_list(self):
        bridge = TabBridge()
        try:
            self.assertEqual(bridge.call({'mode': 'scan', 'windows': [], 'inspect_all': False}), {'tabs': []})
        finally:
            bridge.close()


if __name__ == '__main__':
    unittest.main()
