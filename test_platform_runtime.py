import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from platform_runtime import app_command, capabilities, external_environment, launch_terminal, lock_file, state_directory
from portable_discovery import PortableDiscovery, match_client


class PlatformTests(unittest.TestCase):
    def test_state_override_and_lock_exclude_duplicate_owner(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'CODEX_FLOAT_STATE_DIR': folder}):
            self.assertEqual(state_directory(), Path(folder).resolve())
            path = Path(folder) / 'instance.lock'
            first = lock_file(path)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(lock_file(path))
            finally:
                first.close()
            second = lock_file(path)
            self.assertIsNotNone(second)
            second.close()

    def test_frozen_commands_reenter_launcher_not_embedded_python(self):
        with patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(app_command('codex_float.py', 'serve'), [sys.executable, 'serve'])
            self.assertEqual(app_command('terminal_session.py', '--session', 'abc'),
                             [sys.executable, 'terminal-session', '--session', 'abc'])

    def test_external_processes_do_not_inherit_packaged_library_path(self):
        with patch.object(sys, 'frozen', True, create=True), patch.dict(os.environ,
                {'LD_LIBRARY_PATH':'/package','LD_LIBRARY_PATH_ORIG':'/system'}):
            self.assertEqual(external_environment()['LD_LIBRARY_PATH'], '/system')

    def test_linux_terminal_passes_arguments_without_shell_evaluation(self):
        command = ['/opt/codex float', 'resume', 'value;$(not-a-command)']
        with patch('platform_runtime.sys.platform', 'linux'), patch('platform_runtime.shutil.which', return_value='/bin/xterm'), \
             patch('platform_runtime.subprocess.Popen') as spawn:
            launch_terminal(command, '/tmp/project space')
            self.assertEqual(spawn.call_args.args[0], ['/bin/xterm', '-e', *command])
            self.assertNotIn('shell', spawn.call_args.kwargs)

    def test_macos_launcher_quotes_paths_and_uses_private_script(self):
        with tempfile.TemporaryDirectory() as folder, patch('platform_runtime.sys.platform', 'darwin'), \
             patch('platform_runtime.state_directory', return_value=Path(folder)), patch('platform_runtime.subprocess.run') as run:
            launch_terminal(['/opt/Codex Float', 'resume', "quote'argument"], '/tmp/my project')
            script = Path(run.call_args.args[0][-1])
            content = script.read_text()
            self.assertIn("cd -- '/tmp/my project'", content)
            self.assertIn("exec '/opt/Codex Float' resume 'quote'\"'\"'argument'", content)
            self.assertIn('rm -f -- "$0"', content)
            self.assertEqual(run.call_args.args[0][:3], ['open', '-a', 'Terminal'])

    def test_ambiguous_same_workspace_clients_are_not_assigned_a_session(self):
        clients = [{'pid':1,'provider':'codex','cwd':'/work','created_at':1}]
        threads = [{'id':'a','cwd':'/work'}, {'id':'b','cwd':'/work'}]
        self.assertIsNone(match_client(threads[0], clients, threads))
        clients[0]['session_id'] = 'a'
        self.assertEqual(match_client(threads[0], clients, threads), clients[0])
        self.assertIsNone(match_client(threads[1], clients, threads))

    def test_portable_discovery_detects_closed_sessions_and_pid_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            discovery = PortableDiscovery(Path(folder))
            threads = [{'id':'a','cwd':'/work'}]
            client = {'pid':1,'provider':'codex','cwd':'/work','created_at':1}
            self.assertTrue(discovery.update(threads, [client])['a']['live'])
            self.assertFalse(discovery.update([], [dict(client,created_at=2)])['a']['live'])
            self.assertFalse(discovery.update([], [])['a']['live'])

    def test_capabilities_do_not_claim_unimplemented_native_focus(self):
        self.assertEqual(capabilities()['terminal_tab_focus'], os.name == 'nt')


if __name__ == '__main__':
    unittest.main()
