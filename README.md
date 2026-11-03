# Codex Float

Draggable, always-on-top Windows companions for local Codex chats with turn activity today (Windows local date). A terminal GIF types while a turn runs and sleeps after completion. Positions persist per conversation across restarts. Right-click a companion to turn all companions off.

Double-click a companion to open its exact existing chat using the desktop app's `codex://threads/<id>` link. The selected companion grows to 178 by 152 pixels; all others shrink to 89 by 76 pixels. The selected companion follows the host window's upper-right client area, below the title-bar controls, including when the window moves or resizes. It hides while its host is minimized and reappears on restore. Dragging the selected companion undocks it until you select it again.

For a chat hosted in a separate terminal or editor window, right-click its companion, choose **Vincular: elige una ventana en 8 s**, then focus that window. Subsequent double-clicks restore and activate that bound window. Switching focus between distinctly bound work windows exchanges the full-size companion automatically. When several chats share the same generic desktop window title, the last explicitly selected companion identifies the current chat; changing an internal tab without a distinct native title cannot be detected from window focus alone.

The desktop app must be installed to open chat links ([official deep-link reference](https://learn.chatgpt.com/docs/reference/commands#deep-links)). A manual binding is valid only while the original host window and process still exist; bind it again after restarting the host. This utility never starts another agent or submits a prompt.

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
python -m unittest discover -s . -p "test_*.py" -v
codex-float status
```

The reader opens `CODEX_HOME/state_5.sqlite` (default `~/.codex`) read-only and incrementally scans referenced rollout lifecycle events every two seconds. It excludes archived chats and subagents. Chat content is not retained or sent anywhere. Titles are displayed locally. The internal Codex schema is version-specific; unavailable sources produce a visible disconnected state and an error in `status`, rather than pretending all chats are asleep. A trace lacking a completion or interruption event can retain a working state after an unclean Codex shutdown.

Runtime files: `%LOCALAPPDATA%/CodexFloat` (positions, heartbeat, lock, stop request, startup errors). To uninstall, run `codex-float off`, then remove the launcher and this application folder. Position files may be retained for reinstall.
