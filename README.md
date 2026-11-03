# Codex CLI + floating avatars

Run native Codex CLI sessions in independent Windows terminal windows with draggable animated companions. The ChatGPT/Codex desktop app can remain closed. Each working turn animates a typing terminal; an idle session sleeps. Only native CLI sessions or sessions launched through this utility with activity today are shown, using the Windows local date.

## Install

Requires Windows, Python 3.12 with Tkinter, Pillow, and a signed-in Codex CLI. Windows Terminal is preferred; a standalone console is the fallback.

```powershell
npm install -g @openai/codex
codex login
python -m pip install -r requirements.txt
.\install.ps1
```

The installer writes `codex-float.cmd` into the user's `bin` directory. Keep that directory on PATH. The separately installed npm CLI is preferred. Model, permissions, configuration, and existing hooks are preserved. Normal Codex folder/hook trust prompts still apply; this utility installs no hooks.

## Daily use

```powershell
codex-float new D:\git\my-project
codex-float list
codex-float resume <session-UUID>
codex-float on
codex-float off
codex-float toggle
codex-float status
```

`new` creates a persistent, named conversation through a short-lived local Codex app-server connection, then opens `codex resume <id>` in its own terminal. Creating the conversation does not submit a prompt or model turn. `resume` opens an existing conversation; if its managed terminal is already alive it activates that window instead. A per-session OS lock prevents concurrent managed CLI owners. Launching a session automatically starts the avatars when necessary. `off` stops only the avatars; terminals and agents keep running.

Each managed terminal has a unique fixed title and a dedicated window. Existing native CLI clients in Windows Terminal are also discovered automatically, including resumed chats whose saved source still says `vscode`. Each tab receives its own avatar and native tab identifier. Double-click selects the exact tab; changing tabs exchanges the full-size avatar even when both tabs share one window.

- Double-click an avatar to restore its terminal. If its managed CLI has exited, double-click resumes the conversation in a new terminal.
- The foreground CLI session's avatar is 178x152 pixels; others are 89x76 pixels. When no Codex CLI terminal/tab is active, all avatars return to 178x152 pixels. Switching to another application, minimizing or closing the terminal, or selecting a non-CLI tab clears the highlighted session. Returning to a CLI tab restores the size distinction automatically.
- Closing all terminals keeps today's previously detected companions available at the same normal size. Double-click reopens the corresponding conversation. Sessions from earlier days are excluded.
- The selected avatar follows the upper-right client area below the title-bar controls. Avatars stay visible when their terminal is minimized, keeping their last on-screen position and showing a gray border. Double-click restores the terminal; the selected avatar resumes docking after restoration. Avatars also remain available on the desktop after the terminal closes.
- Dragging a selected avatar undocks it until reselection. Positions persist across avatar restarts.
- Right-click for terminal activation, manual binding, or **Apagar todos**.

## Understand each session

Hover over an avatar for a compact detail card without moving keyboard focus away from the terminal. The card shows the project, current objective, working/resting state, turn duration, latest observed activity, and up to three recent tool outcomes. The floating caption summarizes the current observed phase, such as editing, validation, or investigation.

The latest assistant progress message appears while the turn is working; the latest reported result appears after completion. These are excerpts of what the session communicated, not an independently verified completion claim or a progress percentage. A check mark means a tool reported successful completion or exit code zero; an exclamation mark means it reported failure. Earlier errors remain visible until newer actions replace them.

Move the pointer into the card to read it, choose **Fijar** to keep it open, or close it with **×**. Right-click an avatar and choose **Ver detalles de la sesión** to open it pinned. **Ir a la terminal** selects that session's exact tab. Double-click and dragging keep their existing behavior. Only one detail card opens at a time.

Objective and progress previews are bounded and sanitized locally, retained only in memory, and excluded from runtime status files. Common credential markers cause the whole preview to be omitted; paths, URLs, email addresses, and long opaque identifiers are redacted. Previews still contain ordinary session prose, so consider what is visible when sharing a screen. Raw commands, command output, and reasoning content are never displayed in the card. `codex-float status` includes only fixed activity categories, timestamps, counters, and card state.

## Group placement and global shortcuts

New companions default to a centered row at the top of the monitor, with spacing based on their actual size and additional rows when needed. Adding sessions or changing the active session reflows the automatic group. Dragging a companion removes it from automatic placement and preserves its position across restarts.

The application registers these global shortcuts only when Windows reports the entire group is available:

| Shortcut | Position |
| --- | --- |
| Ctrl+Alt+Up | Top center |
| Ctrl+Alt+Right | Right center |
| Ctrl+Alt+Left | Left center |

Shortcuts reposition all companions on the monitor containing the mouse pointer, reset their manual placements, and keep the group centered and separated. The chosen group position persists. Group placement overrides terminal docking until the next explicit double-click, which can anchor the selected companion to its terminal again. Automatic focus changes preserve the chosen group placement.

If any preferred shortcut is already registered, the application releases partial reservations and tries Ctrl+Alt+Shift with the same arrows. `codex-float status` reports the shortcuts actually registered and any registration error. The same three placements are always available from the avatar's context menu. Shortcuts are released when avatars are turned off.

Plain `codex` clients are matched using their live process workspaces and terminal footer metadata. The initial scan inspects inactive tabs once after at least two seconds without user input, then restores the originally selected tab. Later polls inspect the selected tab and reuse validated tab associations. The helper returns only workspace/title metadata and tab identifiers, without saving terminal transcripts or input. Ambiguous matches are left unassigned; the manual binding option remains available for other console hosts. Active unmanaged turns cannot be resumed into a second CLI.

Starting another CLI client or persisting/renaming a conversation automatically refreshes the tab inspection, even inside an existing terminal window. An inactive new tab is discovered after the next two-second input-idle interval; no avatar restart is required. Ordinary turn timestamp updates do not trigger additional inactive-tab inspections.

## Continue chats from the desktop app

```powershell
codex-float list --all
codex-float resume <session-UUID>
```

Wait for the original turn to finish before moving the conversation to the CLI. Desktop chats are hidden until a live CLI client or launcher registration identifies them. The utility does not close the desktop app or stop its work. WSL sessions in a separate Linux home are not included.

## State and maintenance

The reader opens `CODEX_HOME/state_5.sqlite` (default `~/.codex`) read-only and incrementally scans referenced lifecycle and activity events every two seconds. It excludes archived threads and subagents. Only bounded, sanitized objective/progress excerpts are retained in memory for the detail card; command output and reasoning content are not retained. Thread names are displayed locally. Database and rollout formats are version-specific; unavailable sources produce an error in `status` rather than a false idle result.

Runtime state lives in `%LOCALAPPDATA%/CodexFloat`: positions, window bindings, CLI registrations, per-session locks, heartbeat, and startup errors. Managed CLI wrappers write liveness once per second. A stale wrapper is treated as disconnected. Runtime state, credentials, and conversation logs are excluded from this repository.

Before relocating, stop avatars and finish managed CLI sessions, move the repository, then rerun `install.ps1`. No login startup is installed. To uninstall, stop avatars and managed sessions, then remove the launcher and checkout.

```powershell
python -m unittest discover -s . -p "test_*.py" -v
python generate_assets.py
```

References: [CLI commands](https://learn.chatgpt.com/docs/developer-commands), [local app-server protocol](https://learn.chatgpt.com/docs/app-server), [Windows Terminal arguments](https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments).
