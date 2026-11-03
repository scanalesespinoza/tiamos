"""On-demand local history metadata; never replay transcripts just to build a list."""
from contextlib import closing
import datetime as dt
import heapq
import itertools
import json
import os
from pathlib import Path
import sqlite3
import uuid

from session_activity import safe_preview

LIMIT = 200
BLOCK = 64 * 1024


def history_pin(record):
    """Persist only the structural fields needed to read an explicitly shown session."""
    return {key: record[key] for key in ('id', 'provider', 'session_id', 'cwd', 'config_dir', 'first_seen', 'last_seen')
            if key in record}


def codex_history(codex):
    db = Path(codex) / 'state_5.sqlite'
    if not db.exists():
        return []
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2)) as connection:
        columns = {row[1] for row in connection.execute('PRAGMA table_info(threads)')}
        title = "COALESCE(NULLIF(name,''),title)" if 'name' in columns else 'title'
        rows = connection.execute(f'''SELECT id,{title},cwd,rollout_path,updated_at FROM threads
            WHERE archived=0 AND attached_thread_parent_id IS NULL AND lower(source) NOT LIKE '%subagent%'
            ORDER BY updated_at DESC LIMIT ?''', (LIMIT,)).fetchall()
    records = []
    for ident, title, cwd, path, updated in rows:
        try:
            uuid.UUID(ident)
            if not Path(path).is_file():
                continue
            records.append({'id': ident, 'provider': 'codex', 'title': safe_preview(title or 'Codex', 100),
                            'cwd': cwd, 'updated_at': float(updated)})
        except (ValueError, TypeError, OSError):
            continue
    return records


def claude_record(path, root, modified):
    raw_id = str(uuid.UUID(path.stem))
    size = path.stat().st_size
    with path.open('rb') as stream:
        chunks = [stream.read(BLOCK)]
        if size > BLOCK:
            stream.seek(max(BLOCK, size - BLOCK))
            chunks.append(stream.read(BLOCK))
    cwd, title = None, ''
    custom = False
    for chunk in chunks:
        for line in chunk.splitlines():
            try:
                record = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(record, dict) or record.get('isSidechain'):
                continue
            if record.get('sessionId', record.get('session_id')) != raw_id:
                continue
            if isinstance(record.get('cwd'), str) and record['cwd']:
                cwd = record['cwd']
            if record.get('type') == 'custom-title' and record.get('customTitle'):
                title, custom = safe_preview(record['customTitle'], 100), True
            elif record.get('type') == 'ai-title' and not custom:
                title = safe_preview(record.get('aiTitle') or '', 100)
    if not cwd or not Path(cwd).is_absolute():
        return None
    return {'id': 'claude:' + raw_id, 'session_id': raw_id, 'provider': 'claude',
            'cwd': cwd, 'config_dir': str(root), 'title': title or safe_preview(Path(cwd).name or 'Claude', 80),
            'updated_at': modified, 'first_seen': modified, 'last_seen': modified}


def load_history(codex, claude_roots=()):
    records, warnings = [], []
    try:
        records.extend(codex_history(codex))
    except (OSError, sqlite3.Error):
        warnings.append('No se pudo consultar el historial de Codex.')
    roots = {Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude'),
             *(Path(root) for root in claude_roots)}
    candidates = []
    # Only main-session files, never nested subagent logs. Bound directory metadata work.
    for root in roots:
        for path in itertools.islice((root / 'projects').glob('*/*.jsonl'), 5000):
            try:
                uuid.UUID(path.stem)
                candidates.append((path.stat().st_mtime, str(path), root))
            except (OSError, ValueError):
                continue
    for modified, path, root in heapq.nlargest(LIMIT, candidates, key=lambda item: item[0]):
        try:
            record = claude_record(Path(path), root, modified)
            if record:
                records.append(record)
        except (OSError, ValueError):
            warnings.append('Algunos registros de Claude no están disponibles.')
    # A session UUID in multiple config roots is ambiguous: do not silently pick a source.
    counts = {}
    for record in records:
        counts[record['id']] = counts.get(record['id'], 0) + 1
    records = [record for record in records if counts[record['id']] == 1]
    return sorted(records, key=lambda record: record['updated_at'], reverse=True), list(dict.fromkeys(warnings))


def history_label(record):
    date = dt.datetime.fromtimestamp(record['updated_at']).strftime('%d/%m/%y %H:%M')
    provider = 'Claude' if record['provider'] == 'claude' else 'Codex'
    return date, provider, record['title']
