"""Build on the target OS; archives retain the complete onedir distribution."""
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from platform_runtime import VERSION


def main():
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
                    '--name', 'tiamos', '--distpath', str(ROOT / 'dist'),
                    '--workpath', str(ROOT / 'build'), '--specpath', str(ROOT / 'build'),
                    '--hidden-import', 'PIL._tkinter_finder',
                    '--add-data', str(ROOT / 'terminal_tabs.ps1') + ':.' , str(ROOT / 'tiamos.py')], check=True, cwd=ROOT)
    output = ROOT / 'dist/tiamos'
    if sys.platform == 'win32':
        for name in ('agentlings.cmd', 'codex-float.cmd'):
            (output / name).write_text('@echo off\n"%~dp0tiamos.exe" %*\n', encoding='ascii')
    else:
        for name in ('agentlings', 'codex-float'):
            (output / name).symlink_to('tiamos')
    shutil.copy2(ROOT / 'README.md', output)
    shutil.copy2(ROOT / 'RELEASES.md', output)
    if sys.platform == 'linux':
        shutil.copytree(ROOT / 'linux', output / 'linux', dirs_exist_ok=True)
    arch = platform.machine().lower()
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64'}.get(arch, arch)
    system = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')
    name = f'tiamos-{VERSION}-{system}-{arch}'
    (ROOT / 'release').mkdir(exist_ok=True)
    archive = Path(shutil.make_archive(str(ROOT / 'release' / name), 'zip' if sys.platform == 'win32' else 'gztar',
                                       root_dir=ROOT / 'dist', base_dir='tiamos'))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + '.sha256').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    print(archive)


if __name__ == '__main__':
    main()
