"""Install the optional root-owned, process-metadata observer for one desktop UID."""
import argparse
import os
from pathlib import Path
import pwd
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def install_file(source, destination):
    fd, temporary = tempfile.mkstemp(prefix='.agentlings-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(source.read_bytes())
            os.fchmod(stream.fileno(), 0o644)
            os.fchown(stream.fileno(), 0, 0)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', type=int, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or args.uid <= 0:
        parser.error('Use sudo and specify the non-root desktop UID.')
    pwd.getpwuid(args.uid)
    destination = Path('/usr/local/lib/agentlings-observer')
    destination.mkdir(mode=0o755, exist_ok=True)
    info = destination.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise SystemExit('Observer installation directory must be owned and writable only by root.')
    install_file(ROOT/'elevated_sessions.py', destination/'observer.py')
    unit = Path('/etc/systemd/system/agentlings-observer@.service')
    install_file(ROOT/'linux/agentlings-observer@.service', unit)
    subprocess.run(['systemd-analyze', 'verify', str(unit)], check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    service = f'agentlings-observer@{args.uid}.service'
    subprocess.run(['systemctl', 'enable', service], check=True)
    subprocess.run(['systemctl', 'restart', service], check=True)
    print(f'Installed and started {service}. Desktop data remains in /run and expires after eight seconds.')


if __name__ == '__main__':
    main()
