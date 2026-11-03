import unittest
import sys
import datetime as dt
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
from terminal_discovery import match_session, TabBridge, keep_daily_sessions, discovery_signature, TerminalDiscovery
from window_focus import foreground_selection, avatar_size, FULL_SIZE, HALF_SIZE


class TerminalMatchingTests(unittest.TestCase):
    def test_inactive_third_tab_is_discovered_without_restarting_monitor(self):
        clients = [{'pid': i, 'cwd': f'D:\\project{i}', 'terminal_id': str(i)} for i in range(3)]
        threads = [{'id': str(i), 'cwd': f'D:\\project{i}', 'name': f'Session {i}'} for i in range(3)]
        tabs = [{'hwnd': 123, 'tab_id': str(i), 'selected': i == 0, 'workspace': f'D:\\project{i}', 'title': f'Session {i}'} for i in range(3)]
        requests = []

        def scan(request):
            requests.append(request)
            return {'tabs': tabs if request['inspect_all'] else [tabs[0], dict(tabs[1], workspace=None, title=None), dict(tabs[2], workspace=None, title=None)]}

        monitor = TerminalDiscovery.__new__(TerminalDiscovery)
        monitor.bridge = SimpleNamespace(call=scan)
        monitor.native = SimpleNamespace(all_terminal_windows=lambda: [SimpleNamespace(hwnd=123, pid=42, executable='WindowsTerminal.exe')])
        monitor.cache = {}
        monitor.last_scan_signature = None
        monitor.publish = lambda current, _: current
        with patch('terminal_discovery.native_clients', side_effect=[clients[:2], clients]), patch('terminal_discovery.idle_seconds', return_value=3), patch('terminal_discovery.save'):
            self.assertEqual(set(monitor.update(threads)), {'0', '1'})
            self.assertEqual(set(monitor.update(threads)), {'0', '1', '2'})
        self.assertTrue(requests[1]['inspect_all'])

    def test_new_cli_and_later_session_metadata_invalidate_existing_window_scan(self):
        clients = [{'pid': 10, 'cwd': 'D:\\work', 'terminal_id': 'first'}]
        threads = [{'id': 'a', 'cwd': 'D:\\work', 'name': 'First', 'updated_at': 1}]
        initial = discovery_signature([123], clients, threads)
        added = clients + [{'pid': 20, 'cwd': 'D:\\other', 'terminal_id': 'second'}]
        with_client = discovery_signature([123], added, threads)
        self.assertNotEqual(initial, with_client)
        self.assertNotEqual(with_client, discovery_signature([123], added, threads + [{'id': 'b', 'cwd': 'D:\\other', 'name': 'Second'}]))
        self.assertEqual(initial, discovery_signature([123], clients, [dict(threads[0], updated_at=2)]))

    def test_closed_today_sessions_remain_available_without_active_selection(self):
        now = dt.datetime.now().astimezone()
        records = {
            'a': {'started_at': now.timestamp(), 'cli_pid': 10, 'selected': True},
            'b': {'started_at': now.timestamp(), 'cli_pid': 20, 'selected': False},
            'yesterday': {'started_at': (now - dt.timedelta(days=1)).timestamp(), 'cli_pid': 30},
        }
        result = keep_daily_sessions({}, records, set(), now)
        self.assertEqual(set(result), {'a', 'b'})
        self.assertTrue(all(not record['live'] and not record['selected'] for record in result.values()))
        background = keep_daily_sessions({}, records, {10}, now)
        self.assertTrue(background['a']['live'])
        self.assertFalse(background['a']['selected'])

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

    def test_claude_title_hint_and_codex_footer_share_workspace_without_cross_binding(self):
        clients = [{'pid': 10, 'cwd': 'D:\\work', 'provider': 'codex', 'created_at': 10},
            {'pid': 20, 'cwd': 'D:\\work', 'provider': 'claude', 'created_at': 20}]
        threads = [{'id': 'codex-id', 'cwd': 'D:\\work', 'name': 'Work'},
            {'id': 'claude:id', 'provider': 'claude', 'cwd': 'D:\\work', 'name': 'Claude title', 'cli_pid': 20}]
        tabs = [{'hwnd': 123, 'tab_id': 'codex-tab', 'selected': False, 'provider': 'codex', 'workspace': 'D:\\work', 'title': 'Work'},
            {'hwnd': 123, 'tab_id': 'claude-tab', 'selected': True, 'provider': 'claude', 'workspace': None, 'claude_session': 'claude:id'}]
        monitor = TerminalDiscovery.__new__(TerminalDiscovery)
        monitor.bridge = SimpleNamespace(call=lambda _: {'tabs': tabs})
        monitor.native = SimpleNamespace(all_terminal_windows=lambda: [SimpleNamespace(hwnd=123, pid=42, executable='WindowsTerminal.exe')])
        monitor.cache, monitor.last_scan_signature = {}, None
        monitor.publish = lambda current, _: current
        with patch('terminal_discovery.idle_seconds', return_value=3), patch('terminal_discovery.save'):
            result = monitor.update(threads, clients=clients)
        self.assertEqual(result['codex-id']['tab_id'], 'codex-tab')
        self.assertEqual(result['claude:id']['tab_id'], 'claude-tab')
        self.assertEqual(result['claude:id']['cli_pids'], [20])
        self.assertTrue(result['claude:id']['selected'])
        selected = foreground_selection({key: value['hwnd'] for key, value in result.items() if value['selected']}, 123, 'codex-id')
        self.assertEqual(selected, 'claude:id')
        self.assertEqual(avatar_size('claude:id', selected), FULL_SIZE)
        self.assertEqual(avatar_size('codex-id', selected), HALF_SIZE)
        tabs.append(dict(tabs[1], tab_id='ambiguous-copy', selected=False))
        with patch('terminal_discovery.idle_seconds', return_value=3), patch('terminal_discovery.save'):
            result = monitor.update(threads, clients=clients)
        self.assertEqual(result['claude:id']['kind'], 'unbound')
        self.assertNotIn('tab_id', result['claude:id'])
        self.assertFalse(result['claude:id']['selected'])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows UI Automation transport')
    def test_claude_title_spinners_match_exact_session_without_cross_binding(self):
        script = str(Path(__file__).with_name('terminal_tabs.ps1')).replace("'", "''")
        command = f". '{script}' -MetadataOnly\n" + r'''
$known = @(@{id='claude:one'; title='Example session'})
$result = @()
foreach ($point in @(0x25d0, 0x25d1, 0x25d2, 0x25d3, 0x2733, 0x273b, 0x2801)) {
    $result += Get-ClaudeTabIdentity (([string][char]$point) + ' Example session') $known
}
$result += Get-ClaudeTabIdentity 'Claude Code' $known
$result += Get-ClaudeTabIdentity 'Example session' $known
$result += Get-ClaudeTabIdentity (([string][char]0x25d1) + ' Different session') $known
$result += Get-ClaudeTabIdentity (([string][char]0x25d1) + ' Example session') ($known + @(@{id='claude:two'; title='Example session'}))
ConvertTo-Json -InputObject $result -Compress
'''
        reply = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                               capture_output=True, text=True, check=True, timeout=20)
        results = json.loads(reply.stdout)
        for result in results[:7]:
            self.assertEqual(result, {'provider': 'claude', 'claude_session': 'claude:one'})
        self.assertEqual(results[7]['provider'], 'claude')
        for result in results[8:]:
            self.assertIsNone(result['provider'])
            self.assertIsNone(result['claude_session'])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows UI Automation transport')
    def test_metadata_bridge_handles_empty_window_list(self):
        bridge = TabBridge()
        try:
            self.assertEqual(bridge.call({'mode': 'scan', 'windows': [], 'inspect_all': False}), {'tabs': []})
        finally:
            bridge.close()


if __name__ == '__main__':
    unittest.main()
