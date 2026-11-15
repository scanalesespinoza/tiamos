"""Read-only Codex activity for root clients already scoped to a user's terminal.

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
