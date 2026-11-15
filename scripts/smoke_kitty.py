"""Exercise Kitty's automatic private bridge with two disposable sleep panes.

Run as the desktop user. A temporary Kitty window is opened; no agent is launched
and no existing terminal or configuration is modified.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitty_bridge import request


def main():
    with tempfile.TemporaryDirectory(prefix='tiamos-kitty-') as folder:
        folder = Path(folder); runtime = folder/'runtime'; runtime.mkdir(mode=0o700)
        config = folder/'kitty.conf'; config.write_text(f'linux_display_server x11\nwatcher {ROOT}/kitty_watcher.py\n')
        session = folder/'session'; session.write_text('launch sleep 90\nnew_tab\nlaunch sleep 90\n')
        environment = dict(os.environ, XDG_RUNTIME_DIR=str(runtime))
        previous = os.environ.get('XDG_RUNTIME_DIR'); os.environ['XDG_RUNTIME_DIR'] = str(runtime)
        log = (folder/'kitty.log').open('w')
        process = subprocess.Popen(['kitty','--config',str(config),'--session',str(session)],env=environment,stdout=log,stderr=log)
        try:
            rows=[]
            for _ in range(100):
                try: rows=request('snapshot')['windows']
                except (OSError, ValueError, RuntimeError): pass
                if len(rows)==2: break
                if process.poll() is not None: raise AssertionError('Kitty exited before bridge startup: '+(folder/'kitty.log').read_text()[-1500:])
                time.sleep(.1)
            assert len(rows)==2, 'Automatic watcher did not start bridge'
            for row in rows:
                request('focus',id=row['id'])
                assert next(r['id'] for r in request('snapshot')['windows'] if r['selected'])==row['id']
            try:
                request('send-text',text='must never execute')
                raise AssertionError('Unsupported operation accepted')
            except RuntimeError: pass
            try:
                request('focus',id=999999)
                raise AssertionError('Missing pane accepted')
            except RuntimeError: pass
            print('PASS Kitty watcher autostart, two exact pane selections, rejected unsupported/missing targets')
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
            log.close()
            if previous is None:os.environ.pop('XDG_RUNTIME_DIR',None)
            else:os.environ['XDG_RUNTIME_DIR']=previous


if __name__=='__main__':main()
