import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from linux_desktop import DesktopBridge, LinuxWindows, work_area
from linux_tabs import match_terminal, window_tabs, tabs
from window_focus import Window


def window(ident=1, title='project', pid=40):
    return Window(ident, pid, 'org.gnome.Terminal.desktop', title, (10, 20, 900, 700), True, False)


def tab(ident='tab-a', frame='frame-a', title='project', selected=True):
    return dict(id=ident, pid=40, frame=frame, window_title='project', title=title, selected=selected)


class LinuxDesktopTests(unittest.TestCase):
    def test_unavailable_accessibility_bus_never_enters_native_desktop_reader(self):
        try:
            from gi.repository import Gio
            import pyatspi
        except ImportError:
            self.skipTest('Optional system accessibility modules')
        with patch.object(Gio, 'bus_get_sync', side_effect=RuntimeError('No accessibility bus')), \
             patch.object(pyatspi.Registry, 'getDesktop') as desktop:
            self.assertEqual(tabs(force=True), [])
            desktop.assert_not_called()

    def test_disconnected_compositor_clears_stale_focus_and_shortcuts(self):
        bridge = DesktopBridge()
        bridge.data = {'foreground': 42}
        bridge.labels = {'top': 'Ctrl+Alt+Up'}
        bridge.available = bridge.attached = True
        with patch.object(bridge, 'call', side_effect=RuntimeError('gone')):
            self.assertEqual(bridge.refresh(force=True), {})
        self.assertFalse(bridge.available)
        self.assertFalse(bridge.attached)
        self.assertEqual(bridge.labels, {})

    def test_reconnect_attaches_once_and_delivers_only_known_events(self):
        bridge = DesktopBridge()
        bridge.want_shortcuts = True
        replies = [(json.dumps({'version': 1, 'events': ['top', 'arbitrary']}),),
                   (json.dumps({'labels': {'top': 'Ctrl+Alt+Up'}, 'error': None}),),
                   (json.dumps({'version': 1, 'events': [], 'labels': {'top': 'Ctrl+Alt+Up'}}),)]
        with patch.object(bridge, 'call', side_effect=replies) as call:
            bridge.refresh(force=True)
            bridge.refresh(force=True)
        self.assertEqual([c.args[0] for c in call.call_args_list], ['Snapshot', 'Attach', 'Snapshot'])
        self.assertEqual(bridge.events.get_nowait(), 'top')
        self.assertTrue(bridge.events.empty())

    def test_activation_revalidates_process_identity(self):
        desktop = SimpleNamespace(refresh=Mock(), call=Mock(return_value=(True,)))
        native = LinuxWindows()
        with patch('linux_desktop.bridge', return_value=desktop), patch.object(native, 'inspect', return_value=window(pid=41)):
            self.assertFalse(native.activate(window()))
        desktop.call.assert_not_called()

    def test_monitor_selection_preserves_negative_origins(self):
        desktop = SimpleNamespace(refresh=lambda: {'pointer': [-100, 100],
            'monitors': [[-1600, 30, 0, 900], [0, 30, 1920, 1080]]})
        with patch('linux_desktop.bridge', return_value=desktop):
            self.assertEqual(work_area(), (-1600, 30, 0, 900))
            self.assertEqual(work_area((100, 100)), (0, 30, 1920, 1080))

    def test_duplicate_frame_titles_and_tab_titles_are_not_guessed(self):
        records = [tab(), tab('tab-b', frame='frame-b')]
        self.assertEqual(window_tabs(window(), records), [])
        records = [tab(), tab('tab-b')]
        self.assertEqual(match_terminal({'title': 'project'}, {'terminal_pid': 40}, [window()], records), {})

    def test_exact_inactive_tab_can_be_bound_without_selecting_it(self):
        records = [tab(selected=False), tab('tab-b', title='another')]
        result = match_terminal({'title': 'project'}, {'terminal_pid': 40}, [window()], records)
        self.assertEqual(result['tab_id'], 'tab-a')
        self.assertFalse(result['selected'])

    def test_single_tab_fallback_requires_unique_cli_ownership(self):
        client = {'terminal_pid': 40}
        self.assertEqual(match_terminal({}, client, [window()], [tab()]), {})
        client['terminal_unique'] = True
        self.assertEqual(match_terminal({}, client, [window()], [tab()])['tab_id'], 'tab-a')
        self.assertEqual(match_terminal({}, client, [window(), window(2)], [tab()]), {})


if __name__ == '__main__':
    unittest.main()
