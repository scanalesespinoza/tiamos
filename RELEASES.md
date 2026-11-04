# Desktop releases

The first multi-platform release is **0.3.0-beta.1**. Download an archive and its
`.sha256` file from the repository's GitHub Releases page. Extract the entire
archive; the executable needs its sibling `_internal` directory. Python is bundled.
Codex CLI and Claude CLI are separate installations and must be available on PATH.

| Archive | Target |
| --- | --- |
| `windows-x64.zip` | Windows 10/11 x64 |
| `linux-x64.tar.gz` | Linux x64, glibc 2.35+; X11 or XWayland display |
| `macos-arm64.tar.gz` | macOS 14+ on Apple Silicon |
| `macos-x64.tar.gz` | macOS 15+ on Intel |

Names include `codex-float-<version>-` before the platform. On Windows run
`codex-float.exe on`. On Linux/macOS run `./codex-float on` from the extracted
directory. `off`, `toggle`, `status`, `list`, `new`, `resume`, and `--version` are
also available. No arguments toggles the desktop companions. Add the extracted
directory to PATH if you want to run the command from anywhere.

Windows packages are unsigned. macOS binaries use the build tool's ad-hoc signing;
they are not Developer ID signed or notarized. They are preview CLI distributions,
not `.app`/DMG installers. Managed-device policy may prevent running unsigned
downloads; these packages do not change system security settings.

## Feature coverage

| Feature | Windows | Linux / macOS beta |
| --- | --- | --- |
| Floating draggable avatars, menus, themes, XP profiles, history | Supported | Supported; desktop placement depends on the window manager |
| Activity from today's local Codex/Claude logs | Supported | Supported; Claude discovery scans bounded recent metadata every 30 seconds |
| Notification sounds and volume | Windows audio | macOS `afplay`; Linux `pw-play`, `paplay`, or `aplay` required |
| Exact terminal tab selection and automatic size/docking | Windows Terminal | Not implemented; avatars remain full size, select the CLI tab manually |
| Global arrow shortcuts | Supported | Not implemented; use avatar menu placement and group visibility controls |
| Open/resume closed sessions | Windows Terminal / console | macOS Terminal; Linux x-terminal-emulator, GNOME Terminal, Konsole, XFCE Terminal, or xterm |

The POSIX implementation reads only same-user CLI processes with an attached TTY.
An open transcript UUID takes precedence; otherwise only an unambiguous workspace
match is accepted. Ambiguous processes are not assigned to arbitrary tabs. A live
client in the same workspace prevents automatic duplicate launches. Claude activity
uses transcript lifecycle events instead of Windows-specific process registry fields.
Native Wayland-only operation is not supported by this Tk release: XWayland is needed,
and compositors may restrict topmost positioning. Linux/macOS desktop behavior is
beta pending validation in users' actual terminal/compositor combinations.

State locations: `%LOCALAPPDATA%/CodexFloat` on Windows,
`~/Library/Application Support/CodexFloat` on macOS, and
`${XDG_STATE_HOME:-~/.local/state}/codex-float` on Linux.
`CODEX_FLOAT_STATE_DIR` overrides the state folder for isolated testing.
`CODEX_FLOAT_DISABLE_DISCOVERY=1` disables process/terminal discovery for synthetic
tests; it is not intended for normal CLI monitoring.

## Build and publish

Build **on each target OS** with Python 3.12 and Tk:

```sh
python -m pip install -r requirements-build.txt
python scripts/build_release.py
python scripts/smoke_release.py dist/codex-float/codex-float
```

Use `codex-float.exe` in the last command on Windows. Linux GUI checks run under
`xvfb-run -a` in CI. The workflow tests source behavior, builds the archive, and
starts the actual packaged desktop with a synthetic session, verifies its avatar,
menu, statistics and singleton behavior, then shuts it down. Checksums accompany
each artifact. This does not certify real speaker output or every desktop environment.

Pull requests build all four architectures as downloadable workflow artifacts.
After checks pass and the PR is merged, tag the matching version (`v0.3.0-beta.1`).
The release workflow builds and checks all targets before publishing a single GitHub
prerelease containing all archives and hashes. Version/tag mismatch fails publishing.
Signing/notarization requires separate release credentials and remains future work.
