# Codex and Claude CLI floating avatars

Run native Codex and Claude Code CLI sessions in Windows Terminal with draggable animated companions. The ChatGPT/Codex desktop app can remain closed. Codex companions have a dark blue background; Claude companions have a dark orange background. Each companion has a persistent color and accessory, with gestures for observed activity; an idle session sleeps. Only native CLI sessions or sessions launched through this utility with activity today are shown, using the Windows local date.

## Install

Requires Windows, Python 3.12 with Tkinter, Pillow, and Codex CLI and/or Claude Code CLI. Automatic discovery of existing sessions uses Windows Terminal. Managed Codex launches also support a standalone console fallback.

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
- The foreground CLI session's avatar is 178x152 pixels; others are 89x76 pixels. When no supported CLI terminal/tab is active, all avatars return to 178x152 pixels. Switching to another application, minimizing or closing the terminal, or selecting a non-CLI tab clears the highlighted session. Returning to a CLI tab restores the size distinction automatically.
- Closing all terminals keeps today's previously detected companions available at the same normal size. Double-click reopens the corresponding conversation. Sessions from earlier days are excluded.
- The selected avatar follows the upper-right client area below the title-bar controls. Avatars stay visible when their terminal is minimized, keeping their last on-screen position and showing a gray border. Double-click restores the terminal; the selected avatar resumes docking after restoration. Avatars also remain available on the desktop after the terminal closes.
- Dragging a selected avatar undocks it until reselection. Positions persist across avatar restarts.
- Right-click for terminal activation, manual binding, or **Apagar todos**.

## Colors and live refresh

Provider colors are stored in `%LOCALAPPDATA%\CodexFloat\themes.json`. Background defaults are dark blue `#24364b` for Codex and dark orange `#493326` for Claude. Text and notice colors automatically adapt to the background unless explicitly overridden. Quote hex colors in PowerShell so `#` is not interpreted as a comment.

```powershell
codex-float theme codex --background "#24364b"
codex-float theme claude --background "#493326"
codex-float theme codex --foreground "#f1f5f9" --notice "#ffd18a"
codex-float theme codex --foreground auto --notice auto
codex-float theme edit
codex-float refresh
codex-float theme show
codex-float theme reset
```

`theme edit` opens the JSON file in Notepad. Right-click any avatar for **Editar colores globales** or **Recargar colores**. Saved changes reload automatically in about one second, including sprites at both sizes, text, and unread badges. No avatar or CLI restart is needed, and placement, selection, visibility, and personality remain intact. `refresh` validates the file and confirms the running app has applied the palette; when avatars are off, it prepares colors for the next start. `theme reset` restores dark defaults for both providers.

The JSON accepts `codex` and `claude` objects, each with optional `background`, `foreground`, and `notice` colors in `#RRGGBB` format. Omit `foreground` and `notice` to use automatic contrast. Missing provider settings use defaults. Invalid JSON, unknown keys, and invalid colors keep the last valid live palette; `codex-float status` reports `theme_error`. Fix and save the file to recover automatically. A cold start with an invalid file uses dark defaults. Custom colors are local preferences and are not committed to Git.

## Session levels and a compact team profile

Each avatar displays its session level (`N1`, `N2`, etc.) in the existing title and a two-pixel XP progress bar. Avatar dimensions remain 178×152 / 89×76; there is no additional desktop window or animation. Hover and choose **Perfil · XP**, or right-click **Perfil · nivel y estadísticas**, to replace the activity card with a compact profile. Clicking **Perfil · XP** pins the card so resizing or moving the pointer cannot dismiss it. **Actividad** switches back and keeps it pinned; use **×** to close or **Fijada** to restore hover dismissal. Opening only the profile does not acknowledge an unread work result.

The profile separates **today** (Windows local date) from **available session history**. It shows XP, actions, successful/error/unknown tool outcomes, completed and interrupted turns, today's successful validations/builds, edit actions, waits, API errors, and average completed-turn duration. The tool success percentage includes only known successful/failed non-wait tool results, with the numerator and denominator visible. Unknown outcomes stay separate. A validation count is a classified tool action, not a number of individual test cases; an edit is a tool action, not a file or line count. Duration includes waits and is not CPU time. Missing turn boundaries cannot be counted as completed work.

XP is deterministic and shared by both providers:

| Observed event | XP |
| --- | --- |
| Successful tool action | +2 |
| Action with no explicit outcome | +1 |
| Successful validation/build | +3 additional |
| Explicitly completed turn | +10 |
| Failed action, API error, waiting, or interrupted turn | No bonus |

Action XP is capped at 50 per turn; completion adds up to 10 more. Actions without an observed active turn earn no XP and are excluded from this profile. Previously earned action XP is retained when a turn is interrupted. Level L starts at `50 × L × (L − 1)` total XP: level 2 at 100 XP, level 3 at 300, level 4 at 600. There are no rankings, penalties, or notifications. Volume and tool outcomes are signals for understanding activity, not certification of task quality, correctness, or business impact.

Counters reuse the existing incremental transcript readers. There is no second scan, polling loop, model call, database, or new background process. Memory holds numeric lifetime aggregates plus at most eight local day buckets and bounded recent turn IDs. Restarting rebuilds the same aggregates from the available session transcript; repeated polls do not add the same events again. If logs are removed, truncated, compacted, or unavailable, levels describe the remaining readable history rather than an independent permanent score. Resuming the same session retains the level as long as its history remains available; a new session starts separately. Provider log formats and event coverage can differ, so raw totals are not a fair leaderboard between agents. `codex-float status` includes numeric `statistics`, without commands, tool output, objectives, or result prose.

## Understand each session

Claude sessions already running in Windows Terminal are discovered without restarting them or installing hooks. The adapter validates the interactive session's PID and Windows process creation time against Claude's local session registry, and reads its reported state. Conversation titles, including automatic title changes, help associate the exact tab. Namespaced identities keep Codex and Claude separate even in the same workspace. Ambiguous tab matches remain unassigned rather than selecting another session. Windows Terminal title overrides or older Claude versions without the local session registry can prevent automatic binding.

The adapter reads top-level Claude JSONL records incrementally for bounded objective/progress/result previews and fixed tool categories. Subagent records, API request payloads, reasoning, and tool output are not retained. Recognized idle/working metadata determines liveness; unsupported states without lifecycle evidence show **Sin estado**. API failures and interrupted turns do not produce a success celebration. Claude's local formats are version-specific.

Both providers share dragging, focus sizing, docking, hide/show, detail cards, quiet mode, and personalization. Today's closed Claude sessions remain available; double-click resumes them with `claude --resume <session-id>` in their original workspace. The existing `new`, `list`, and `resume` launcher commands remain Codex commands. Claude authentication, Vertex settings, and hooks are left unchanged.

Each session keeps its own color and accessory across restarts. Companions read a book while exploring, type or hold a pencil while editing, show moving test lights during validation, and hold a wrench after an observed tool error. These gestures describe activity categories, not the agent's thoughts or proof that a task succeeded. A short wave acknowledges explicit terminal selection; dragging produces a small reaction inside the avatar without moving the window by itself.

An explicit wait on a tool shows an hourglass and **Esperando**. The session remains working; this does not imply that it needs user input or has stalled. Ordinary silence alone never triggers a waiting or error claim.

Right-click and choose **Personalizar compañero** to select one of eight colors and four accessories for that session. Changes apply immediately at both sizes and persist across restarts. **Restablecer aspecto automático** returns to an automatically assigned available combination. Automatic assignment avoids occupied combinations while space remains; deliberate custom choices may match another session.

A newly completed turn gets a three-second celebration and an amber **new result** dot. The dot remains until you open that session's detail card or successfully activate its terminal, including across avatar restarts. A new working turn does not erase an unread prior result. Interrupted turns do not celebrate or create a result notice; neither do startup history or turns whose latest tool reported an error celebrate. A normal completed turn may still require follow-up: the celebration marks the end of the turn, not independently verified success.

Right-click any avatar and enable **Modo tranquilo** to freeze animations and suppress waves/confetti for all companions. Colors, activity captions, result dots, hover cards, dragging, and terminal selection remain available. The setting persists across restarts. There are no sounds or autonomous desktop movement.

Hover over an avatar for a compact detail card without moving keyboard focus away from the terminal. The card shows the project, current objective, working/resting state, turn duration, latest observed activity, and up to three recent tool outcomes. The floating caption summarizes the current observed phase, such as editing, validation, or investigation.

The latest assistant progress message appears while the turn is working; the latest reported result appears after completion. These are excerpts of what the session communicated, not an independently verified completion claim or a progress percentage. A check mark means a tool reported successful completion or exit code zero; an exclamation mark means it reported failure. If the latest tool failed, an amber message explains that outcome while preserving the session's working state. A later successful action clears the message; earlier errors remain in the recent history until newer actions replace them. Empty optional sections are hidden.

When a new turn begins, the card also retains the previous completed turn's reported result in a separate section. This makes an unread prior result available alongside current progress. If that turn had no final message, the card says so instead of presenting progress as a final result. Only one bounded, sanitized prior result is retained, in memory; it is excluded from runtime state files.

Move the pointer into the card to read it, choose **Fijar** to keep it open, or close it with **×**. Right-click an avatar and choose **Ver detalles de la sesión** to open it pinned. **Ir a la terminal** selects that session's exact tab. Double-click and dragging keep their existing behavior. Only one detail card opens at a time.

If session updates become unavailable, the card explicitly marks its information as stale and freezes an active turn's observed duration at the last successful update. Historical actions and reported progress remain readable. Normal timing and state return automatically when reading recovers.

Objective and progress previews are bounded and sanitized locally, retained only in memory, and excluded from runtime status files. Common credential markers cause the whole preview to be omitted; paths, URLs, email addresses, and long opaque identifiers are redacted. Fenced code blocks and inline code are omitted from prose previews. Previews still contain ordinary session prose, so consider what is visible when sharing a screen. Tool commands, tool output, and reasoning content are never displayed in the card. `codex-float status` includes only fixed activity categories, timestamps, counters, and card state.

## Group placement and global shortcuts

New companions default to a centered row at the top of the monitor, with spacing based on their actual size and additional rows when needed. Adding sessions or changing the active session reflows the automatic group. Dragging a companion removes it from automatic placement and preserves its position across restarts.

The application registers these global shortcuts only when Windows reports the entire group is available:

| Shortcut | Position |
| --- | --- |
| Ctrl+Alt+Up | Top center |
| Ctrl+Alt+Right | Right center |
| Ctrl+Alt+Left | Left center |
| Ctrl+Alt+Down | Hide/show all avatars |

**Ctrl+Alt+Down** temporarily hides every avatar and the detail card; press it again to restore them. Sessions keep running, positions are retained, and newly discovered companions remain hidden until you restore the group. Placement shortcuts can still reposition the hidden group. Restarting the avatar application starts visible. When the visibility shortcut is registered, **Ocultar avatares** is also available in the context menu.

Placement shortcuts reposition all companions on the monitor containing the mouse pointer, reset their manual placements, and keep the group centered and separated. The chosen group position persists. Group placement overrides terminal docking until the next explicit double-click, which can anchor the selected companion to its terminal again. Automatic focus changes preserve the chosen group placement.

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

Runtime state lives in `%LOCALAPPDATA%/CodexFloat`: positions, window bindings, CLI registrations, per-session locks, heartbeat, startup errors, identity slots, result/acknowledgment timestamps, and the quiet preference. Companion notices store no result text. Managed CLI wrappers write liveness once per second. A stale wrapper is treated as disconnected. Runtime state, credentials, and conversation logs are excluded from this repository.

Before relocating, stop avatars and finish managed CLI sessions, move the repository, then rerun `install.ps1`. No login startup is installed. To uninstall, stop avatars and managed sessions, then remove the launcher and checkout.

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```

References: [CLI commands](https://learn.chatgpt.com/docs/developer-commands), [local app-server protocol](https://learn.chatgpt.com/docs/app-server), [Windows Terminal arguments](https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments).

Claude reference: [CLI commands and resume](https://code.claude.com/docs/en/cli-reference). Current companion sprites are generated in memory by `avatar_personality.py`; the legacy GIF generator is not used by the live renderer.
