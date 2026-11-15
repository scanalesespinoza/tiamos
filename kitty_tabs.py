"""Exact Kitty pane binding through a user-owned, focus-only bridge."""
import time
from kitty_bridge import request

_cache = (0, [])


def tabs(force=False):
    global _cache
    if not force and time.monotonic() < _cache[0]: return _cache[1]
    try: rows = request('snapshot')['windows']
    except (OSError, ValueError, RuntimeError): rows = []
    _cache = (time.monotonic()+.3, rows)
    return rows


def match_terminal(client, windows, records=None):
    rows = tabs() if records is None else records
    matches = [r for r in rows if r['pid'] == client.get('shell_pid')
               and r['terminal_pid'] == client.get('terminal_pid')]
    if len(matches) != 1: return {}
    pane = matches[0]
    # Multiple native windows need an explicit platform identity; never guess.
    if len({r['os_window'] for r in rows if r['terminal_pid']==pane['terminal_pid']}) != 1: return {}
    hosts = [w for w in windows if w.pid == pane['terminal_pid']]
    if len(hosts) != 1: return {}
    w = hosts[0]
    return {'kind':'tab','hwnd':w.hwnd,'window_pid':w.pid,'executable':w.executable,
            'tab_id':f"kitty:{pane['id']}",'selected':pane['selected'],
            'shell_pid':pane['pid']}


def tab_selected(window, ident):
    return any(ident == f"kitty:{r['id']}" and r['terminal_pid']==window.pid and r['selected'] for r in tabs())


def select_tab(record):
    from linux_desktop import LinuxWindows
    native = LinuxWindows(); window = native.inspect(record.get('hwnd'))
    if not window or window.pid != record.get('window_pid'):
        raise RuntimeError('La ventana original ya no está disponible.')
    rows = tabs(force=True)
    candidates = [r for r in rows if record.get('tab_id')==f"kitty:{r['id']}"
        and r['terminal_pid']==window.pid and r['pid']==record.get('shell_pid')]
    if len(candidates) != 1: raise RuntimeError('La pestaña original ya no está disponible.')
    try: request('focus', id=candidates[0]['id'])
    except (OSError, ValueError, RuntimeError) as error:
        raise RuntimeError('Kitty no permitió seleccionar la pestaña.') from error
    if not native.activate(window): raise RuntimeError('El escritorio no permitió activar la terminal.')
    tabs(force=True)
