"""Start Agentlings' private bridge on Kitty's first window resize."""
from pathlib import Path
import time


def on_resize(boss, window, data):
    now = time.monotonic()
    if now - getattr(boss, '_agentlings_bridge_attempt', -10) < 10:
        return
    boss._agentlings_bridge_attempt = now
    boss.remote_control_script(str(Path(__file__).with_name('kitty_bridge.py')))
