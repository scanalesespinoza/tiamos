# Codex Float

Draggable, always-on-top Windows companions for local Codex chats with turn activity today (Windows local date). A terminal GIF types while a turn runs and sleeps after completion. Positions persist per conversation across restarts. Right-click a companion to turn all companions off.

```powershell
codex-float on
codex-float off
codex-float toggle
codex-float status
```

Python 3.12 with Tkinter and Pillow runs the application. Regenerate the included GIFs with `python generate_assets.py`. Starting twice preserves a single instance. No login startup is installed.

## Install or relocate

Clone or move the repository to the desired directory, then run:

```powershell
python -m pip install -r requirements.txt
.\install.ps1
codex-float on
```

The installer writes `codex-float.cmd` into the user's `bin` directory, pointing to this checkout and the selected Python interpreter. Keep that directory on PATH. Before relocating an existing installation, run `codex-float off`; rerun `install.ps1` from the new location. Runtime state and saved positions stay outside the repository.

## Verify

```powershell
python -m unittest discover -s . -p test_reader.py -v
codex-float status
```

The reader opens `CODEX_HOME/state_5.sqlite` (default `~/.codex`) read-only and incrementally scans referenced rollout lifecycle events every two seconds. It excludes archived chats and subagents. Chat content is not retained or sent anywhere. Titles are displayed locally. The internal Codex schema is version-specific; unavailable sources produce a visible disconnected state and an error in `status`, rather than pretending all chats are asleep. A trace lacking a completion or interruption event can retain a working state after an unclean Codex shutdown.

Runtime files: `%LOCALAPPDATA%/CodexFloat` (positions, heartbeat, lock, stop request, startup errors). To uninstall, run `codex-float off`, then remove the launcher and this application folder. Position files may be retained for reinstall.
