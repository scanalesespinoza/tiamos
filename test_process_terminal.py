import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import psutil

from process_terminal import controlling_terminal


class TerminalIdentityTests(unittest.TestCase):
    def test_linux_stat_handles_parentheses_and_disappearing_processes(self):
        process = SimpleNamespace(pid=42)
        with patch('process_terminal.sys.platform', 'linux'):
            for text, expected in [('42 (a ) b) S 1 2 3 34818 0', 34818),
                                   ('42 (server) S 1 2 3 0 0', None), ('invalid', None)]:
                with self.subTest(text=text), patch.object(Path, 'read_text', return_value=text):
                    self.assertEqual(controlling_terminal(process), expected)
            with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
                self.assertIsNone(controlling_terminal(process))

    def test_other_platforms_keep_native_terminal_lookup(self):
        with patch('process_terminal.sys.platform', 'darwin'):
            self.assertEqual(controlling_terminal(SimpleNamespace(terminal=lambda: '/dev/ttys001')),
                             '/dev/ttys001')

    @unittest.skipUnless(sys.platform == 'linux', 'Live Linux PTY regression')
    def test_both_discoverers_observe_tabs_opened_after_the_first_scan(self):
        import pty
        from elevated_sessions import collect
        from portable_discovery import native_clients

        # Prime psutil before allocating new terminal devices, just as the
        # long-running monitor does before the user opens additional tabs.
        psutil.Process().terminal()
        processes, fds, clients = [], [], []
        terminal = SimpleNamespace(pid=os.getpid(), name=lambda: 'kitty',
                                   uids=lambda: SimpleNamespace(real=1000), create_time=lambda: 1)
        try:
            for index in range(3):
                master, slave = pty.openpty()
                fds.extend((master, slave))
                child = subprocess.Popen([sys.executable, '-c',
                    'import os, fcntl, termios, time; os.setsid(); '
                    'fcntl.ioctl(0, termios.TIOCSCTTY, 0); time.sleep(30)'],
                    stdin=slave, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(child)
                process = psutil.Process(child.pid)
                deadline = time.monotonic() + 5
                while controlling_terminal(process) is None and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(controlling_terminal(process), os.fstat(slave).st_rdev)
                # Only provider and ancestry are synthetic; terminal identity
                # comes from the real child and newly allocated kernel PTY.
                clients.append(SimpleNamespace(pid=child.pid, info={'name': 'codex'},
                    name=lambda: 'codex', uids=lambda: SimpleNamespace(real=0),
                    parents=lambda: [terminal], create_time=process.create_time,
                    cwd=lambda: '/test', open_files=lambda: []))
                self.assertEqual(len(collect(1000, clients)['sessions']), index + 1)
                with patch('portable_discovery.os.getuid', return_value=0), \
                     patch('portable_discovery.psutil.process_iter', return_value=clients):
                    self.assertEqual(len(native_clients()), index + 1)
            # No controlling terminal means no avatar, even with valid ancestry.
            background = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                start_new_session=True, stdin=subprocess.DEVNULL)
            processes.append(background)
            clients[0].pid = background.pid
            self.assertEqual(len(collect(1000, clients)['sessions']), 2)
        finally:
            for child in processes:
                child.terminate()
                child.wait(timeout=5)
            for fd in fds:
                os.close(fd)


if __name__ == '__main__':
    unittest.main()
