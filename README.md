# Agentlings

Your CLI agents, at a glance: floating teammates with activity, experience, and gentle notifications.

Formerly **Codex Float**. The command is now `agentlings`; `codex-float` remains a compatibility alias. Existing installations reuse their original state folder and locks, keeping positions, themes, history, and sound preferences. Fresh installations use the `Agentlings` state folder (`agentlings` on Linux). The legacy `CODEX_FLOAT_*` environment settings remain accepted; `AGENTLINGS_*` takes precedence. Repository: [scanalesespinoza/agentlings](https://github.com/scanalesespinoza/agentlings).

**Windows, Linux, and macOS release packages:** see [RELEASES.md](RELEASES.md) for downloads, installation, architecture requirements, and the feature matrix. Linux now has optional [GNOME desktop integration](#linux-gnome-desktop-integration) for terminal focus, docking and global shortcuts. Other Linux desktops and macOS retain portable behavior. The Windows-specific workflow below continues to apply to the full Windows integration.

## Linux GNOME desktop integration

The source installation supports GNOME on Wayland (with XWayland for Tk) and X11 through a small Shell extension. It adds terminal activation/restoration, focus-dependent avatar sizing, docking to terminal geometry, monitor work areas and global shortcuts. Exact tab selection is available for GNOME Terminal through its accessibility metadata; terminal contents are never read. Other recognized terminals can be associated manually at the window level.

On Fedora, install dependencies and then run the installer **as your desktop user**:

```sh
sudo dnf install python3-tkinter python3-pillow-tk python3-psutil python3-gobject python3-pyatspi gnome-terminal
python3 scripts/install_linux.py --gnome-extension --autostart
agentlings on
```

The installer copies the source application to `~/.local/share/agentlings/app`, adds `~/.local/bin/agentlings` and a desktop launcher, and preserves the existing runtime preferences. `--autostart` is optional. The extension is installed under `~/.local/share/gnome-shell/extensions/agentlings@agentlings.local`; existing enabled extensions are preserved. **Log out and back in once after installing or updating the extension.** It cannot be loaded into an already running GNOME Shell by restarting only Agentlings. The installer does not end your desktop session or enable Shell unsafe mode. Run `agentlings off` before updating an existing installation.

With the extension available, `agentlings status` reports `capabilities.desktop_mode: "gnome"` and actual registered shortcuts. It tries the complete Ctrl+Alt+arrow group, then Ctrl+Alt+Shift+arrows, then Super+Ctrl+Alt+arrows. GNOME commonly reserves the first two groups for workspaces. Conflicting reservations are released before trying another group; existing desktop bindings are never overwritten. Shortcuts work in normal desktop mode, are released when Agentlings stops (including a crashed client), and are not installed permanently in desktop settings. Use the avatar menu if all groups are occupied.

Automatic tab association requires one unique exact tab title and a validated terminal-process ancestor, or a single terminal window with one tab and one CLI client. Multiple candidates remain unbound. For an ambiguous session, right-click its avatar, choose the existing manual binding action, and select its terminal tab within eight seconds. That binding remembers the selected GNOME Terminal tab, so double-clicking the avatar restores the same tab. Closed or replaced tab identities are rejected. Window IDs, process identity and current tab selection are checked before focus; a live CLI is never duplicated just because its window cannot be identified.

Without the extension or optional Python desktop dependencies, Agentlings continues in `portable-beta` mode and reports the missing integration. Native Wayland integration on KDE/wlroots and exact tabs in terminals other than GNOME Terminal are not implemented. Fractional scaling and mixed-scale monitors still require validation; the local walkthrough covered GNOME 50 at 100% scale. Binary release packages remain portable unless built with the optional system desktop modules; the source installation above is the validated integration path.

To disable just the integration:

```sh
gnome-extensions disable agentlings@agentlings.local
```

The regression suite and real desktop walkthrough can be run locally:

```sh
python3 -m unittest discover -s . -p 'test_*.py' -q
# Additional Fedora test prerequisite:
sudo dnf install dbus-daemon
python3 scripts/smoke_linux_desktop.py
```

The walkthrough creates a private D-Bus session, GNOME compositor and virtual monitor. It selects two real GNOME Terminal tabs, tests focus sizing, minimization/restoration, double-click docking, following changed window geometry, global hide/show/placement shortcuts and shortcut cleanup. Sessions and input are synthetic; no agent or model is launched, and the operator's desktop settings and input are untouched. The original portable smoke test remains available as `scripts/smoke_release.py`.

Run native Codex and Claude Code CLI sessions in Windows Terminal with draggable animated companions. The ChatGPT/Codex desktop app can remain closed. Codex companions have a dark blue background; Claude companions have a dark orange background. Each companion has a persistent color and accessory, with gestures for observed activity; an idle session sleeps. Only native CLI sessions or sessions launched through this utility with activity today are shown, using the Windows local date.

## Install

Requires Windows, Python 3.12 with Tkinter, Pillow, and Codex CLI and/or Claude Code CLI. Automatic discovery of existing sessions uses Windows Terminal. Managed Codex launches also support a standalone console fallback.

```powershell
npm install -g @openai/codex
codex login
python -m pip install -r requirements.txt
.\install.ps1
```

The installer writes `agentlings.cmd` into the user's `bin` directory. Keep that directory on PATH. The separately installed npm CLI is preferred. Model, permissions, configuration, and existing hooks are preserved. Normal Codex folder/hook trust prompts still apply; this utility installs no hooks.

## Daily use

```powershell
agentlings new D:\git\my-project
agentlings list
agentlings resume <session-UUID>
agentlings on
agentlings off
agentlings toggle
agentlings status
```

`new` creates a persistent, named conversation through a short-lived local Codex app-server connection, then opens `codex resume <id>` in its own terminal. Creating the conversation does not submit a prompt or model turn. `resume` opens an existing conversation; if its managed terminal is already alive it activates that window instead. A per-session OS lock prevents concurrent managed CLI owners. Launching a session automatically starts the avatars when necessary. `off` stops only the avatars; terminals and agents keep running.

Each managed terminal has a unique fixed title and a dedicated window. Existing native CLI clients in Windows Terminal are also discovered automatically, including resumed chats whose saved source still says `vscode`. Each tab receives its own avatar and native tab identifier. Double-click selects the exact tab; changing tabs exchanges the full-size avatar even when both tabs share one window.

- Double-click an avatar to restore its terminal. If its managed CLI has exited, double-click resumes the conversation in a new terminal.
- The foreground CLI session's avatar is 178x152 pixels; others are 89x76 pixels. When no supported CLI terminal/tab is active, all avatars return to 178x152 pixels. Switching to another application, minimizing or closing the terminal, or selecting a non-CLI tab clears the highlighted session. Returning to a CLI tab restores the size distinction automatically.
- Closing all terminals keeps today's previously detected companions available at the same normal size. Double-click reopens the corresponding conversation. Sessions from earlier days are excluded.
- The selected avatar follows the upper-right client area below the title-bar controls. Avatars stay visible when their terminal is minimized, keeping their last on-screen position and showing a gray border. Double-click restores the terminal; the selected avatar resumes docking after restoration. Avatars also remain available on the desktop after the terminal closes.
- Dragging a selected avatar undocks it until reselection. Positions persist across avatar restarts.
- Right-click for terminal activation, manual binding, or **Apagar todos**.

Opening a context menu hides the hover card and suspends automatic hover details across all avatars until the menu and its submenus close. Normal hover resumes after dismissal. Explicit detail/profile menu actions still open the requested card.

## Colors and live refresh

Provider colors are stored in `%LOCALAPPDATA%\Agentlings\themes.json`. Background defaults are dark blue `#24364b` for Codex and dark orange `#493326` for Claude. Text and notice colors automatically adapt to the background unless explicitly overridden. Quote hex colors in PowerShell so `#` is not interpreted as a comment.

```powershell
agentlings theme codex --background "#24364b"
agentlings theme claude --background "#493326"
agentlings theme codex --foreground "#f1f5f9" --notice "#ffd18a"
agentlings theme codex --foreground auto --notice auto
agentlings theme edit
agentlings refresh
agentlings theme show
agentlings theme reset
```

`theme edit` opens the JSON file in Notepad. Right-click any avatar for **Editar colores globales** or **Recargar colores**. Saved changes reload automatically in about one second, including sprites at both sizes, text, and unread badges. No avatar or CLI restart is needed, and placement, selection, visibility, and personality remain intact. `refresh` validates the file and confirms the running app has applied the palette; when avatars are off, it prepares colors for the next start. `theme reset` restores dark defaults for both providers.

The JSON accepts `codex` and `claude` objects, each with optional `background`, `foreground`, and `notice` colors in `#RRGGBB` format. Omit `foreground` and `notice` to use automatic contrast. Missing provider settings use defaults. Invalid JSON, unknown keys, and invalid colors keep the last valid live palette; `agentlings status` reports `theme_error`. Fix and save the file to recover automatically. A cold start with an invalid file uses dark defaults. Custom colors are local preferences and are not committed to Git.

## Group menu and previous sessions

A 36-pixel circular **⋮** button follows the end of the automatic avatar group, including wrapped rows/columns. For a fully manual group it stays near the last companion, avoiding overlap where space permits. It remains available when avatars are hidden or there are no sessions. The button is a control, not an extra session.

Its border is mint while any session is working, amber when a working session explicitly requests intervention or its latest tool action failed, and gray otherwise. Tool waits alone do not request attention; unavailable sessions do not contribute stale alerts. The menu shows working/resting/unknown counts and visible/total avatars, including hidden sessions in activity counts. These observations reuse the existing one-second refresh; the button and avatar sizes are unchanged.

- **Ocultar avatares / Mostrar avatares** toggles the whole group. Ctrl+Alt+Down uses the same state; the circle stays visible to restore the group.
- **Avatares visibles** chooses individual companions. These choices persist across restarts and are preserved while the whole group is hidden.
- **Mostrar todos los avatares** restores every currently listed companion, clearing their individual hidden choices and the temporary group hide.
- **Ubicación**, **Modo tranquilo**, **Sonidos**, and **Apagar Agentlings** remain reachable from the group menu even when no avatars are visible. Placement shows the registered shortcuts where supported.
- **Sesiones anteriores…** opens a searchable list of available local sessions with date, provider, and title. Select a row and choose **Mostrar avatar** (or double-click the row). This adds its avatar without opening or resuming a CLI. Double-click the avatar separately to activate/resume its terminal using the existing live-client safeguards.
- **Volver a sesiones de hoy** removes explicit historical additions; today's sessions remain. Historical additions persist across restarts until cleared.

The history picker focuses search when opened. Use Down to select a result, Enter to show its avatar, and Escape to close. Filtering preserves a selection that still matches. Loading, no history, and no search matches have separate messages; read warnings remain visible while filtering. Showing an avatar is disabled during loading and requires a valid selection; sessions already added are excluded.

The history list is loaded only on request, in a short-lived background worker, with no recurring history scan. It reads up to 200 unarchived top-level Codex metadata rows and up to 200 recent main-session Claude files, inspecting at most 5,000 file entries per configuration root and only the first/last 64 KiB of each selected file. It excludes missing Codex logs, Claude records without usable session/workspace metadata, nested subagents, and ambiguous Claude UUIDs across roots. It does not retain conversation prose, tool output, or commands. Some Claude titles or records outside those bounded metadata samples may be unavailable. Already shown sessions are managed from **Avatares visibles** rather than duplicated in history. Visibility selections live in `visibility.json`; explicit historical identities/workspaces live in `shown-history.json`, both under the local runtime directory.

## Observed session states

The caption, details, group summary, inbox and input sounds share the same interpretation of explicit session evidence. A request for your response uses a speech bubble, a tool wait uses an hourglass, an interrupted turn uses a pause symbol, and unavailable activity uses a question mark. Completed turns say **Turno terminado**; completion does not certify the result or its validation. Compact companions use shorter versions of these labels.

Agentlings never infers a need for human input from elapsed time. Missing or stale data does not become completion, interruption or a new request. A known closed terminal remains **CLI cerrado** and can be resumed. The `companions` section in `agentlings status` includes the interpreted `status` alongside the displayed sprite.

The activity card also shows the last observed test/build check, its reported outcome and age, and whether file edits were observed afterward. A tool's reported success does not establish test coverage or certify the current workspace. Unknown outcomes remain unknown. These summaries use the existing fixed activity categories, retain only one check and one edit in memory, and reconstruct from the existing session reader without storing commands or output or launching any checks. Equal timestamps preserve observed event order. The CLI exposes this metadata under `activity.<session>.verification`.

## Attention inbox

Open **⋮ → Necesita tu atención…** to review explicit requests for input, observed tool errors, interrupted turns, and unread results in one list. The group ring remains amber while notices are pending, including hidden companions. Enter opens the selected available session; **Marcar visto** or Ctrl+Enter acknowledges an error, interruption, or result. Escape closes the inbox. Requests for input must be answered in their original terminal and cannot be dismissed as resolved here. An ordinary tool wait never becomes a request for human input.

Errors and interruptions observed after initial discovery remain until acknowledged, even after recovery or a monitor restart. First discovery establishes a baseline for historical errors and interruptions. The latest event of each kind is retained for up to 128 sessions; timestamps and acknowledgment watermarks are saved in `attention.json`, without titles, commands, paths, or conversation text. Result notices use the existing acknowledgment behavior and are listed for currently shown sessions. Unavailable sessions are marked as stale and cannot be opened from an old inbox row.

The inbox creates its window only when opened, reuses the existing update loop, and does no rendering while hidden. It adds no transcript scan, background worker, polling timer, or dependency. A tool error is an observed event, not a declaration that the whole task failed; a completed turn still needs human review.

Avatar painting applies only changed widget properties. Hidden companions keep observing their sessions and recording notices, but skip animation generation and painting. Quiet mode keeps a still frame without repeatedly resending it to Tk. Native window observations are shared only within one UI tick; opening a session always validates its window afresh.

To compare desktop overhead locally, run `python scripts/benchmark_desktop.py --sessions 6 --seconds 10`, then repeat with `--quiet` and `--hidden`. The benchmark uses temporary synthetic sessions and its own isolated monitor. It reports CPU as a percentage of one core and peak sampled resident memory after warmup; use matching settings on the same machine. It does not scan operator sessions or apply a hardware-dependent CI threshold.

## Starred companions

Right-click an avatar and open **Starred → Destacar avatar** to mark it with a star. Choose **Estrella**, **Círculo**, **Rombo**, **Triángulo**, **Cuadrado**, or **Hexágono** in that submenu to change the marker; choosing a symbol also enables it. Uncheck **Destacar avatar** to remove the marker while remembering the selected symbol. Choices are per session for both Codex and Claude and persist in `starred.json` under the runtime state directory.

The small amber shape sits **left of a right-side stack**, **below a top stack**, or **right of a left-side stack**. Dragged or terminal-docked companions use the current group placement direction. It follows movement and full/half size, hides with its avatar, and stays visible when the associated terminal is minimized. Automatic wrapping reserves marker space without covering neighboring companions, levels, or status text. Avatar content remains 178×152 / 89×76; markers are 18 / 14 pixels with a four-pixel gap. On Linux/macOS the marker has a small background matching its avatar.

The marker itself accepts right-click for the same session menu and double-click for terminal activation. These are personal visual labels, not scores or unread-result indicators. Shapes use native canvas geometry with one small window only for each marked avatar, reuse the existing UI tick, and add no process, dependency, or polling timer. Removing a marker releases its window; hidden marked sessions retain the preference.

## Session levels and a compact team profile

Each avatar displays its session level (`N1`, `N2`, etc.) in the existing title and a two-pixel XP progress bar. Avatar dimensions remain 178×152 / 89×76; there is no additional desktop window or animation. Hover and choose **Perfil · XP**, or right-click **Perfil · nivel y estadísticas**, to replace the activity card with a compact profile. Clicking **Perfil · XP** pins the card so resizing or moving the pointer cannot dismiss it. **Actividad** switches back and keeps it pinned; use **×** to close or **Fijada** to restore hover dismissal. Opening only the profile does not acknowledge an unread work result.

The profile separates **today** (Windows local date) from **available session history**. It shows XP, actions, successful/error/unknown tool outcomes, completed and interrupted turns, today's successful validations/builds, edit actions, waits, API errors, and average completed-turn duration. The tool success percentage includes only known successful/failed non-wait tool results, with the numerator and denominator visible. Unknown outcomes stay separate. A validation count is a classified tool action, not a number of individual test cases; an edit is a tool action, not a file or line count. Duration includes waits and is not CPU time. Missing turn boundaries cannot be counted as completed work.

The profile opens in a compact **Gráfica** view. Its line shows accumulated XP at the last seven explicitly closed turns, with amber points for interrupted turns; ongoing-turn XP remains visible in the level header. A single closed turn is a point rather than an invented trend. The vertical axis fits the visible XP range, so slope is not a cross-session comparison. The adjacent outcome trend compares the last three closed turns with the previous three, in percentage points (pp), showing both sample sizes. It requires six closed turns and at least five known tool outcomes in each group; otherwise it reports insufficient data. This is a descriptive change, not proof of skill improvement or statistical significance.

Five horizontal bars show observed tool success rates for validation/builds, editing, exploration, delivery/Git, and other tools. Unknown outcomes are excluded from the denominator. The star marks the highest rate among areas with at least five known results, including ties, and never marks a zero rate. Counts remain visible so a tiny sample is not mistaken for demonstrated expertise. **Cifras** switches to the numeric profile, and **Gráfica** returns; both stay pinned and reuse the same card. Avatar dimensions are unchanged. Charts use a fixed native Tk canvas, keep only seven turn summaries and five numeric area buckets, and redraw only when chart data or the accent changes. No plotting library, extra process, transcript scan, or animation timer is added.

XP is deterministic and shared by both providers:

| Observed event | XP |
| --- | --- |
| Successful tool action | +2 |
| Action with no explicit outcome | +1 |
| Successful validation/build | +3 additional |
| Explicitly completed turn | +10 |
| Failed action, API error, waiting, or interrupted turn | No bonus |

Action XP is capped at 50 per turn; completion adds up to 10 more. Actions without an observed active turn earn no XP and are excluded from this profile. Previously earned action XP is retained when a turn is interrupted. Level L starts at `50 × L × (L − 1)` total XP: level 2 at 100 XP, level 3 at 300, level 4 at 600. There are no rankings, penalties, or notifications. Volume and tool outcomes are signals for understanding activity, not certification of task quality, correctness, or business impact.

Counters reuse the existing incremental transcript readers. There is no second scan, polling loop, model call, database, or new background process. Memory holds numeric lifetime aggregates plus at most eight local day buckets and bounded recent turn IDs. Restarting rebuilds the same aggregates from the available session transcript; repeated polls do not add the same events again. If logs are removed, truncated, compacted, or unavailable, levels describe the remaining readable history rather than an independent permanent score. Resuming the same session retains the level as long as its history remains available; a new session starts separately. Provider log formats and event coverage can differ, so raw totals are not a fair leaderboard between agents. `agentlings status` includes numeric `statistics`, without commands, tool output, objectives, or result prose.

## Understand each session

Claude sessions already running in Windows Terminal are discovered without restarting them or installing hooks. The adapter validates the interactive session's PID and Windows process creation time against Claude's local session registry, and reads its reported state. Conversation titles, including automatic title changes, help associate the exact tab. Namespaced identities keep Codex and Claude separate even in the same workspace. Ambiguous tab matches remain unassigned rather than selecting another session. Windows Terminal title overrides or older Claude versions without the local session registry can prevent automatic binding.

The adapter reads top-level Claude JSONL records incrementally for bounded objective/progress/result previews and fixed tool categories. Subagent records, API request payloads, reasoning, and tool output are not retained. Recognized idle/working metadata determines liveness; unsupported states without lifecycle evidence show **Sin estado**. API failures and interrupted turns do not produce a success celebration. Claude's local formats are version-specific.

Both providers share dragging, focus sizing, docking, hide/show, detail cards, quiet mode, and personalization. Today's closed Claude sessions remain available; double-click resumes them with `claude --resume <session-id>` in their original workspace. The existing `new`, `list`, and `resume` launcher commands remain Codex commands. Claude authentication, Vertex settings, and hooks are left unchanged.

Each session keeps its own color and accessory across restarts. Companions read a book while exploring, type or hold a pencil while editing, show moving test lights during validation, and hold a wrench after an observed tool error. These gestures describe activity categories, not the agent's thoughts or proof that a task succeeded. A short wave acknowledges explicit terminal selection; dragging produces a small reaction inside the avatar without moving the window by itself.

Companions have softly shaded shells, inset glass faces, subtle highlights, and smooth contours at both sizes. Brief blinks accompany active gestures; resting, waiting, and carried companions have distinct expressions. Artwork is drawn locally and cached, preserving custom backgrounds, the existing animation cadence, and quiet mode's still, open-eyed active face.

An explicit wait on a tool shows an hourglass and **Esperando**. The session remains working; this does not imply that it needs user input or has stalled. Ordinary silence alone never triggers a waiting or error claim.

Right-click and choose **Personalizar compañero** to select one of eight colors and four accessories for that session. Changes apply immediately at both sizes and persist across restarts. **Restablecer aspecto automático** returns to an automatically assigned available combination. Automatic assignment avoids occupied combinations while space remains; deliberate custom choices may match another session.

A newly completed turn gets a three-second celebration and an amber **new result** dot. The dot remains until you open that session's detail card or successfully activate its terminal, including across avatar restarts. A new working turn does not erase an unread prior result. Interrupted turns do not celebrate or create a result notice; neither do startup history or turns whose latest tool reported an error celebrate. A normal completed turn may still require follow-up: the celebration marks the end of the turn, not independently verified success.

Right-click any avatar and enable **Modo tranquilo** to freeze animations and suppress waves/confetti and notification sounds for all companions. Colors, activity captions, result dots, hover cards, dragging, and terminal selection remain available. The setting persists across restarts. There is no autonomous desktop movement.

### Notification sounds

Open **⋮ → Sonidos**, or right-click any avatar and choose **Sonidos**, to enable/disable audio, select **Volumen** (0, 10, 25, 50, 75, or 100%), or choose **Probar sonido**. Sounds start enabled at 25%. Settings persist in `sounds.json`; they control only this application's audio, not Windows volume. Quiet mode temporarily suppresses sounds without changing that preference. Hiding avatars does not mute their notifications.

Four brief, soft synthesized chimes distinguish a newly completed turn, an observed tool/API error, an explicit request for intervention, and a level increase. Completion is an observed lifecycle event, not a certification that the work is correct. Interrupted turns and completions whose last tool failed do not play the completion chime. Intervention is announced only when the provider exposes the explicit **Esperando intervención** state (currently Claude); ordinary tool waits and inactivity do not imply a request for help.

Startup, first discovery of a session, and historical records are silent. Only subsequent fresh events notify. Simultaneous events produce one chime, prioritizing intervention, error, level, then completion. Automatic playback is limited to one chime per three seconds, with repeated errors limited to one per session per twenty seconds. Suppressed events are not queued or replayed after unmuting. **Modo tranquilo** also disables the preview until it is turned off.

Playback uses Windows asynchronous audio and short local WAV files generated on demand (at most four files, under 120 KB total). It adds no audio dependency, worker process, or polling timer. `agentlings status` exposes the sound preference, volume, quiet suppression, and any playback error; an unavailable audio device does not stop the avatars.

Hover over an avatar for a compact detail card without moving keyboard focus away from the terminal. The card shows the project, current objective, working/resting state, turn duration, latest observed activity, and up to three recent tool outcomes. The floating caption summarizes the current observed phase, such as editing, validation, or investigation.

The latest assistant progress message appears while the turn is working; the latest reported result appears after completion. These are excerpts of what the session communicated, not an independently verified completion claim or a progress percentage. A check mark means a tool reported successful completion or exit code zero; an exclamation mark means it reported failure. If the latest tool failed, an amber message explains that outcome while preserving the session's working state. A later successful action clears the message; earlier errors remain in the recent history until newer actions replace them. Empty optional sections are hidden.

When a new turn begins, the card also retains the previous completed turn's reported result in a separate section. This makes an unread prior result available alongside current progress. If that turn had no final message, the card says so instead of presenting progress as a final result. Only one bounded, sanitized prior result is retained, in memory; it is excluded from runtime state files.

Move the pointer into the card to read it, choose **Fijar** to keep it open, or close it with **×**. Right-click an avatar and choose **Ver detalles de la sesión** to open it pinned. **Ir a la terminal** selects that session's exact tab. Double-click and dragging keep their existing behavior. Only one detail card opens at a time.

If session updates become unavailable, the card explicitly marks its information as stale and freezes an active turn's observed duration at the last successful update. Historical actions and reported progress remain readable. Normal timing and state return automatically when reading recovers.

Objective and progress previews are bounded and sanitized locally, retained only in memory, and excluded from runtime status files. Common credential markers cause the whole preview to be omitted; paths, URLs, email addresses, and long opaque identifiers are redacted. Fenced code blocks and inline code are omitted from prose previews. Previews still contain ordinary session prose, so consider what is visible when sharing a screen. Tool commands, tool output, and reasoning content are never displayed in the card. `agentlings status` includes only fixed activity categories, timestamps, counters, and card state.

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

If any preferred shortcut is already registered, the application releases partial reservations and tries Ctrl+Alt+Shift with the same arrows. `agentlings status` reports the shortcuts actually registered and any registration error. The same three placements are always available from the avatar's context menu. Shortcuts are released when avatars are turned off.

Plain `codex` clients are matched using their live process workspaces and terminal footer metadata. The initial scan inspects inactive tabs once after at least two seconds without user input, then restores the originally selected tab. Later polls inspect the selected tab and reuse validated tab associations. The helper returns only workspace/title metadata and tab identifiers, without saving terminal transcripts or input. Ambiguous matches are left unassigned; the manual binding option remains available for other console hosts. Active unmanaged turns cannot be resumed into a second CLI.

Starting another CLI client or persisting/renaming a conversation automatically refreshes the tab inspection, even inside an existing terminal window. An inactive new tab is discovered after the next two-second input-idle interval; no avatar restart is required. Ordinary turn timestamp updates do not trigger additional inactive-tab inspections.

## Continue chats from the desktop app

```powershell
agentlings list --all
agentlings resume <session-UUID>
```

Wait for the original turn to finish before moving the conversation to the CLI. Desktop chats are hidden until a live CLI client or launcher registration identifies them. The utility does not close the desktop app or stop its work. WSL sessions in a separate Linux home are not included.

## State and maintenance

The reader opens `CODEX_HOME/state_5.sqlite` (default `~/.codex`) read-only and incrementally scans referenced lifecycle and activity events every two seconds. It excludes archived threads and subagents. Only bounded, sanitized objective/progress excerpts are retained in memory for the detail card; command output and reasoning content are not retained. Thread names are displayed locally. Database and rollout formats are version-specific; unavailable sources produce an error in `status` rather than a false idle result.

Runtime state lives in `%LOCALAPPDATA%/Agentlings`: positions, window bindings, CLI registrations, per-session locks, heartbeat, startup errors, identity slots, result/acknowledgment timestamps, and the quiet preference. Companion notices store no result text. Managed CLI wrappers write liveness once per second. A stale wrapper is treated as disconnected. Runtime state, credentials, and conversation logs are excluded from this repository.

Before relocating, stop avatars and finish managed CLI sessions, move the repository, then rerun `install.ps1`. No login startup is installed. To uninstall, stop avatars and managed sessions, then remove the launcher and checkout.

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```

References: [CLI commands](https://learn.chatgpt.com/docs/developer-commands), [local app-server protocol](https://learn.chatgpt.com/docs/app-server), [Windows Terminal arguments](https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments).

Claude reference: [CLI commands and resume](https://code.claude.com/docs/en/cli-reference). Current companion sprites are generated in memory by `avatar_personality.py`; the legacy GIF generator is not used by the live renderer.
