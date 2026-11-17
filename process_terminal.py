"""Current controlling-terminal identity, including newly allocated Linux PTYs."""
from pathlib import Path
import sys


def controlling_terminal(process):
    if sys.platform != 'linux':
        return process.terminal()
    # psutil's Linux terminal() resolves tty_nr through a cached /dev map.
    # A long-running observer must also recognize PTYs created after that map.
    # Read only process metadata; never open the terminal or its contents.
    try:
        stat = Path(f'/proc/{process.pid}/stat').read_text()
        # comm is parenthesized and can itself contain spaces or parentheses.
        device = int(stat.rsplit(')', 1)[1].split()[4])
    except (OSError, ValueError, IndexError):
        return None
    return device or None
