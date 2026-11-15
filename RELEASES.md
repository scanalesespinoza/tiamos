# Desktop releases

Download from [Agentlings releases](https://github.com/scanalesespinoza/agentlings/releases).

The Agentlings release is **0.3.0-beta.6** (formerly Codex Float). Download an archive and its
`.sha256` file from the repository's GitHub Releases page. Extract the entire
archive; the executable needs its sibling `_internal` directory. Python is bundled.
Codex CLI and Claude CLI are separate installations and must be available on PATH.

## Changes in beta.6

- The cap accessory has a rounded crown, an asymmetric visor, a small badge, and shading matched to the companion's accent. The silhouette stays recognizable at full and half size; existing cap selections update automatically.
- Antennas have a defined mount and a shaded round tip; headphones have an arched padded band and distinct ear cushions; ears have a larger pointed silhouette and contrasting inner panels. All accessories follow the existing accent palette and keep the same sprite dimensions and animation timing.

## Previous changes in beta.5

- Starred markers stay out of the Windows taskbar and do not take keyboard focus. Tool-window settings survive transparency changes, switching shapes/themes, and hiding/restoring markers.

## Previous changes in beta.4

- Right-click **Starred** to highlight any Codex or Claude companion with a star (default), circle, diamond, triangle, square, or hexagon. Symbol selection and enabled state persist per session.
- Markers follow the group direction: left of right stacks, below top stacks, and right of left stacks. Full/half sizing, dragging, visibility, and automatic wrapping account for the marker without covering avatar content.
- Uses native geometry and the existing UI tick, with no new dependencies, background processes, or polling timers. A small marker window exists only for marked avatars.

## Previous changes in beta.3

- The existing group button shows a discreet activity/attention border and its menu summarizes observed team state and avatar visibility.
- Restore all hidden companions in one action, reposition the group, toggle quiet mode, or stop Agentlings even when no avatars are visible.
- History distinguishes loading, empty history, and unmatched searches, preserves read warnings and valid selection, and supports Down/Enter/Escape navigation. Loading and stale selections cannot add duplicate avatars.
- No larger avatars, additional polling timer, dependency, or background process is introduced. Native group/history tests now run on all release operating systems.

| Archive | Target |
| --- | --- |
| `windows-x64.zip` | Windows 10/11 x64 |
| `linux-x64.tar.gz` | Linux x64, glibc 2.35+; X11 or XWayland display |
| `macos-arm64.tar.gz` | macOS 14+ on Apple Silicon |
| `macos-x64.tar.gz` | macOS 15+ on Intel |

Names include `agentlings-<version>-` before the platform. On Windows run
`agentlings.exe on`. On Linux/macOS run `./agentlings on` from the extracted
directory. `off`, `toggle`, `status`, `list`, `new`, `resume`, and `--version` are
also available. No arguments toggles the desktop companions. Add the extracted
directory to PATH if you want to run the command from anywhere.

Windows packages are unsigned. macOS binaries use the build tool's ad-hoc signing;
they are not Developer ID signed or notarized. They are preview CLI distributions,
not `.app`/DMG installers. Managed-device policy may prevent running unsigned
downloads; these packages do not change system security settings.

## Feature coverage

The current source branch also offers optional GNOME integration via
`python3 scripts/install_linux.py --gnome-extension --autostart`; see the
[Linux installation and local tests](README.md#linux-gnome-desktop-integration).
The published beta archives described below retain portable behavior. Source
integration was exercised locally on GNOME 50/Wayland at 100% scale, including
real tab selection, focus sizing, minimization/restoration, docking, shortcuts
and releasing shortcut reservations. Other compositors and fractional scaling
are not certified by that walkthrough.

| Feature | Windows | Linux / macOS beta |
| --- | --- | --- |
| Floating draggable avatars, menus, themes, XP profiles, history | Supported | Supported; desktop placement depends on the window manager |
| Activity from today's local Codex/Claude logs | Supported | Supported; Claude discovery scans bounded recent metadata every 30 seconds |
| Notification sounds and volume | Windows audio | macOS `afplay`; Linux `pw-play`, `paplay`, or `aplay` required |
| Exact terminal tab selection and automatic size/docking | Windows Terminal | GNOME source integration: GNOME Terminal tabs, focus sizing and docking; portable packages/macOS: manual tab selection |
| Global arrow shortcuts | Supported | GNOME source integration: collision-aware native shortcuts; portable packages/macOS: use avatar menu |
| Open/resume closed sessions | Windows Terminal / console | macOS Terminal; Linux x-terminal-emulator, GNOME Terminal, Konsole, XFCE Terminal, or xterm |

The POSIX implementation reads only same-user CLI processes with an attached TTY.
An open transcript UUID takes precedence; otherwise only an unambiguous workspace
match is accepted. Ambiguous processes are not assigned to arbitrary tabs. A live
client in the same workspace prevents automatic duplicate launches. Claude activity
uses transcript lifecycle events instead of Windows-specific process registry fields.
Native Wayland-only operation is not supported by this Tk release: XWayland is needed,
and compositors may restrict topmost positioning. Linux/macOS desktop behavior is
beta pending validation in users' actual terminal/compositor combinations.

State locations: `%LOCALAPPDATA%/Agentlings` on Windows,
`~/Library/Application Support/Agentlings` on macOS, and
`${XDG_STATE_HOME:-~/.local/state}/agentlings` on Linux.
Existing installations continue using their original `CodexFloat` folder (`codex-float`
on Linux), including its singleton lock, so the old and new commands control the same
avatars. No configuration is copied or deleted. Archives include a `codex-float`
compatibility command; use `agentlings` for new integrations. The old `CODEX_FLOAT_*`
environment names remain aliases; `AGENTLINGS_*` wins when both are set.
`AGENTLINGS_STATE_DIR` overrides the state folder for isolated testing.
`AGENTLINGS_DISABLE_DISCOVERY=1` disables process/terminal discovery for synthetic
tests; it is not intended for normal CLI monitoring.

## Build and publish

Pull requests build and smoke-test every platform without retaining downloadable
artifacts. Tagged releases and manual workflow runs retain their packages. This
keeps validation independent of artifact-storage quota while preserving release
uploads as a required step for publishing.

Build **on each target OS** with Python 3.12 and Tk:

```sh
python -m pip install -r requirements-build.txt
python scripts/build_release.py
python scripts/smoke_release.py dist/agentlings/agentlings
```

Use `agentlings.exe` in the last command on Windows. Linux GUI checks run under
`xvfb-run -a` in CI. The workflow tests source behavior, builds the archive, and
starts the actual packaged desktop with a synthetic session, verifies its avatar,
menu, statistics and singleton behavior, then shuts it down. Checksums accompany
each artifact. This does not certify real speaker output or every desktop environment.

Pull requests build all four architectures as downloadable workflow artifacts.
After checks pass and the PR is merged, tag the matching version (`v0.3.0-beta.6`).
The release workflow builds and checks all targets before publishing a single GitHub
prerelease containing all archives and hashes. Version/tag mismatch fails publishing.
Signing/notarization requires separate release credentials and remains future work.
