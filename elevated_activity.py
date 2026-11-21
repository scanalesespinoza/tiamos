"""Read-only Codex and Claude activity for root clients already scoped to a user's terminal.

Shared-server clients do not hold rollout files. Correlate their latest rendered
assistant text with exactly one rollout. No fuzzy/cwd match or activity inferred
from CPU use. Raw text stays in the observer; only normal sanitized summaries
leave it. Missing or ambiguous evidence deliberately yields unknown.
"""
from collections import deque
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from claude_trace import ClaudeTrace, valid_session
from session_activity import safe_preview, text_content
from session_trace import Trace


def unique_match(stream, messages):
    # Require the newest text, so an old conversation cannot mask a tab switch.
    for size in (256, 128, 80):
        if len(stream) < size:
            continue
        needle = stream[-size:]
        matches = [ident for ident, texts in messages.items() if any(needle in text for text in texts)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return None


class CodexActivity:
    def __init__(self, home=Path('/root/.codex')):
        self.home = Path(home)
        self.traces = {}
        self.messages = {}

    def enrich(self, records):
        codex = [r for r in records if r['provider'] == 'codex']
        if not codex:
            return
        with closing(sqlite3.connect((self.home/'state_5.sqlite').as_uri()+'?mode=ro', uri=True, timeout=.5)) as db:
            rows = db.execute('SELECT id, rollout_path, COALESCE(NULLIF(name,\'\'),title), cwd FROM threads '
                'WHERE archived=0 AND attached_thread_parent_id IS NULL ORDER BY updated_at DESC LIMIT 100').fetchall()
        metadata = {}
        for ident, path, title, cwd in rows:
            path = Path(path).resolve()
            if not path.is_relative_to((self.home/'sessions').resolve()):
                continue
            try:
                stamp = path.stat().st_mtime_ns
                if ident not in self.messages or self.messages[ident][0] != stamp:
                    # Bound scans even for long histories; never inspect tool output.
                    with path.open('rb') as f:
                        f.seek(max(0, path.stat().st_size-4*1024*1024))
                        lines = f.read().splitlines()
                    texts = deque(maxlen=128)
                    for line in lines:
                        try:
                            item = json.loads(line); payload = item.get('payload', {})
                            if item.get('type') == 'response_item' and payload.get('role') == 'assistant':
                                texts.append(text_content(payload.get('content')))
                            elif item.get('type') == 'event_msg' and payload.get('type') == 'agent_message':
                                texts.append(payload.get('message', ''))
                        except (ValueError, TypeError, AttributeError):
                            continue
                    self.messages[ident] = (stamp, list(texts))
                metadata[ident] = (path, title, cwd)
            except OSError:
                continue
        messages = {ident:self.messages[ident][1] for ident in metadata}
        with closing(sqlite3.connect((self.home/'logs_2.sqlite').as_uri()+'?mode=ro', uri=True, timeout=.5)) as db:
            for record in codex:
                # Birth bound prevents PID reuse from inheriting an old stream.
                logs = db.execute("SELECT feedback_log_body FROM logs WHERE process_uuid GLOB ? "
                    "AND thread_id IS NULL AND ts>=? AND target='codex_tui::markdown_stream' "
                    "ORDER BY id DESC LIMIT 600", (f"pid:{record['pid']}:*", int(record['created_at']))).fetchall()
                chunks = []
                for body, in reversed(logs):
                    if body.startswith('push_delta: '):
                        try:
                            chunk = json.loads(body[12:])
                            if isinstance(chunk, str): chunks.append(chunk)
                        except ValueError:
                            pass
                ident = unique_match(''.join(chunks)[-4096:], messages)
                if not ident:
                    continue
                path, title, cwd = metadata[ident]
                trace = self.traces.get(ident)
                if trace is None or trace.path != path:
                    trace = self.traces[ident] = Trace(path)
                try:
                    trace.read()
                except OSError:
                    continue
                record['chat'] = {'id': ident, 'title': safe_preview(title or 'Codex', 100),
                    'project': safe_preview(Path(cwd).name, 60),
                    'state': 'working' if trace.active else 'sleeping',
                    'activity': trace.activity.summary()}
        self.messages = {k:v for k,v in self.messages.items() if k in metadata}
        live = {r.get('chat', {}).get('id') for r in records}
        self.traces = {k:v for k,v in self.traces.items() if k in live}


CLAUDE_WORKING = {'busy', 'working', 'running', 'thinking'}
CLAUDE_WAITING = {'waiting', 'needs_input', 'waiting_for_permission', 'waiting_for_input'}
MAX_SESSION_BYTES = 64 * 1024


class ClaudeActivity:
    """Claude CLI keeps one metadata file per live process, so no text correlation is needed.

    The record must match the process identity (pid, interactive CLI, start time), and the
    transcript must be a single file under the root config dir. Anything else stays unknown.
    """

    def __init__(self, home=Path('/root/.claude')):
        self.home = Path(home)
        self.traces = {}

    def session(self, record):
        path = self.home/'sessions'/f"{record['pid']}.json"
        if path.stat().st_size > MAX_SESSION_BYTES:
            return None
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) and valid_session(data, record) else None

    def enrich(self, records):
        live = set()
        for record in records:
            if record['provider'] != 'claude':
                continue
            try:
                data = self.session(record)
            except (OSError, ValueError):
                continue
            if not data:
                continue
            session_id = data['sessionId']
            paths = list((self.home/'projects').glob(f'*/{session_id}.jsonl'))
            trace = self.traces.get(session_id)
            if len(paths) == 1 and (trace is None or trace.path != paths[0]):
                trace = self.traces[session_id] = ClaudeTrace(paths[0], session_id)
            if trace is not None:
                try:
                    trace.read()
                except OSError:
                    trace = None
            live.add(session_id)
            activity = trace.activity.summary() if trace else {}
            status = data.get('status')
            if status in CLAUDE_WORKING:
                state = 'working'
            elif status in CLAUDE_WAITING:
                state, activity['phase'] = 'working', 'Esperando intervención'
            elif status == 'idle':
                state = 'sleeping'
            elif trace is not None:
                state = 'working' if trace.active else 'sleeping'
            else:
                continue
            # A name the user set (/rename) wins over the transcript's generated title.
            named = data.get('name') if data.get('nameSource') == 'user' else ''
            title = named or (trace.title if trace else '') or data.get('name') or 'Claude'
            record['chat'] = {'id': f'claude:{session_id}', 'title': safe_preview(title, 100),
                'project': safe_preview(Path(data.get('cwd') or '').name, 60),
                'state': state, 'activity': activity}
        self.traces = {k: v for k, v in self.traces.items() if k in live}
