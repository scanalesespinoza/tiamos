"""Bounded GNOME Terminal tab metadata via the desktop accessibility API.

Only frame titles, tab header labels, identities and selection state are read.
Terminal widgets and text interfaces are never queried. Exact, unique matches
are required; inaccessible/ambiguous tabs remain unbound.
"""
import time

_cache = (0, [])


def _label(tab):
    if tab.name:
        return tab.name
    for child in list(tab)[:16]:
        if child.getRoleName() == 'label' and child.name:
            return child.name
        if child.getRoleName() in ('panel', 'filler'):
            for label in list(child)[:16]:
                if label.getRoleName() == 'label' and label.name:
                    return label.name
    return ''


def tabs(force=False):
    global _cache
    if not force and time.monotonic() < _cache[0]:
        return _cache[1]
    result = []
    try:
        # libatspi aborts the process if the accessibility bus cannot be opened.
        # Probe it with a bounded D-Bus request before asking for the desktop.
        from gi.repository import Gio
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        connection.call_sync('org.a11y.Bus', '/org/a11y/bus', 'org.a11y.Bus',
            'GetAddress', None, None, Gio.DBusCallFlags.NONE, 250, None)
        import pyatspi
        from gi.repository import Atspi
        Atspi.set_timeout(150, 250)
        for app in list(pyatspi.Registry.getDesktop(0))[:128]:
            if app.name != 'org.gnome.Terminal':
                continue
            pid = app.get_process_id()
            for frame in list(app)[:32]:
                pending = [(frame, 0)]
                budget = 128
                while pending and budget:
                    node, depth = pending.pop()
                    budget -= 1
                    role = node.getRoleName()
                    if role == 'page tab list':
                        for tab in list(node)[:128]:
                            if tab.getRoleName() != 'page tab':
                                continue
                            result.append({'id': f'{pid}:{frame.path}:{tab.path}',
                                'pid': pid, 'frame': frame.path, 'window_title': frame.name,
                                'title': _label(tab),
                                'selected': tab.getState().contains(pyatspi.STATE_SELECTED),
                                'node': tab})
                        continue
                    # Never descend into a terminal or into a tab's terminal page.
                    if depth < 5 and role in ('frame', 'panel', 'filler', 'root pane', 'scroll pane'):
                        pending.extend((child, depth+1) for child in list(node)[:32])
    except Exception:
        result = []
    _cache = (time.monotonic() + .2, result)
    return result


def window_tabs(window, records=None):
    candidates = [tab for tab in (tabs() if records is None else records)
                  if tab['pid'] == window.pid and tab['window_title'] == window.title]
    # Multiple identically titled frames cannot safely be assigned a native ID.
    return candidates if len({tab['frame'] for tab in candidates}) == 1 else []


def selected_tab(window):
    candidates = [tab for tab in window_tabs(window) if tab['selected']]
    return candidates[0]['id'] if len(candidates) == 1 else None


def tab_selected(window, ident):
    if str(ident).startswith('kitty:'):
        from kitty_tabs import tab_selected as selected
        return selected(window, ident)
    return selected_tab(window) == ident


def select_tab(record):
    if str(record.get('tab_id', '')).startswith('kitty:'):
        from kitty_tabs import select_tab as select
        return select(record)
    from linux_desktop import LinuxWindows
    native = LinuxWindows()
    window = native.inspect(record.get('hwnd'))
    if not window or window.pid != record.get('window_pid'):
        raise RuntimeError('La ventana original ya no está disponible.')
    candidates = [tab for tab in window_tabs(window, tabs(force=True)) if tab['id'] == record.get('tab_id')]
    if len(candidates) != 1:
        raise RuntimeError('La pestaña original ya no está disponible o su identidad es ambigua.')
    tab = candidates[0]['node']
    if not tab.parent.querySelection().selectChild(tab.getIndexInParent()):
        raise RuntimeError('La terminal no permitió seleccionar la pestaña.')
    if not native.activate(window):
        raise RuntimeError('El escritorio no permitió activar la terminal.')


def match_terminal(thread, client, windows, records=None):
    """Use a unique exact tab title, or a single-tab terminal ancestor.

    There is no fuzzy title matching, tab cycling, text scraping or guessing
    among multiple CLI sessions in a workspace.
    """
    if not windows:
        return {}
    records = tabs() if records is None else records
    matches = []
    title = thread.get('title') or thread.get('name')
    for window in windows:
        if window.pid != client.get('terminal_pid'):
            continue
        candidates = window_tabs(window, records)
        for tab in candidates:
            if title and tab['title'] == title:
                matches.append((window, tab))
    if not matches:
        owned = [w for w in windows if w.pid == client.get('terminal_pid')]
        if len(owned) == 1:
            candidates = window_tabs(owned[0], records)
            if len(candidates) == 1 and client.get('terminal_unique', False):
                matches = [(owned[0], candidates[0])]
    if len(matches) != 1:
        return {}
    window, tab = matches[0]
    return {'kind': 'tab', 'hwnd': window.hwnd, 'window_pid': window.pid,
            'executable': window.executable, 'tab_id': tab['id'], 'selected': tab['selected']}
