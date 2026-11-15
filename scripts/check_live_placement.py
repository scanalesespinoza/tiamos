"""Verify requested placement shortcuts in the user's active GNOME session.

Moves the existing avatars through both cycles, restarts only Agentlings to
check persistence, then restores the original placement. Never restarts agents,
Kitty, or the desktop. Run as the desktop user after installing this version.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from avatar_layout import PLACEMENT_CYCLE
from platform_runtime import state_directory


def main():
    from gi.repository import Gio, GLib
    def state():
        try: return json.loads((state_directory()/'status.json').read_text())
        except (OSError, ValueError): return {}
    def until(check):
        for _ in range(100):
            if check(): return
            time.sleep(.1)
        raise AssertionError('Expected live placement state did not appear')
    initial = state(); original = initial['layout']
    assert initial['hotkeys'] == {'cycle_next':'Ctrl+Alt+Page_Down', 'cycle_previous':'Ctrl+Alt+Page_Up'}
    bindings = Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
    def unrelated():
        return [p for p in bindings.get_strv('custom-keybindings') if '/agentlings-cycle_' not in p]
    other_bindings = unrelated()
    wm = Gio.Settings.new('org.gnome.desktop.wm.keybindings')
    workspace_keys = {key:wm.get_value(key) for key in wm.list_keys() if 'workspace' in key}
    connection = Gio.bus_get_sync(Gio.BusType.SESSION,None)
    name = 'org.gnome.Mutter.RemoteDesktop'
    def call(path, iface, method, signature=None, values=()):
        return connection.call_sync(name,path,iface,method,
            GLib.Variant(signature,values) if signature else None,None,0,2000,None).unpack()
    session=call('/org/gnome/Mutter/RemoteDesktop',name,'CreateSession')[0];iface=name+'.Session'
    call(session,iface,'Start')
    def step(direction):
        current = state()['layout']
        expected = PLACEMENT_CYCLE[(PLACEMENT_CYCLE.index(current)+direction)%3]
        keys=[0xffe3,0xffe9,0xff56 if direction==1 else 0xff55]
        for key in keys:call(session,iface,'NotifyKeyboardKeysym','(ub)',(key,True))
        for key in reversed(keys):call(session,iface,'NotifyKeyboardKeysym','(ub)',(key,False))
        until(lambda: state().get('layout')==expected)
        s=state();left,top,right,bottom=s['layout_area']
        for ident,(x,y) in s['windows'].items():
            if not s['visible'].get(ident):continue
            width,height=s['sizes'][ident]
            assert left<=x and top<=y and x+width<=right and y+height<=bottom
        assert not s['hotkey_error'] and not s['error']
        print('PASS', 'AvPág' if direction==1 else 'RePág', expected, flush=True)
    try:
        for direction in (1,1,1,-1,-1,-1):step(direction)
        while state()['layout']!='bottom':step(1)
        app=Path.home()/'.local/bin/agentlings'
        subprocess.run([str(app),'off'],check=True,timeout=15)
        assert all('/agentlings-cycle_' not in p for p in bindings.get_strv('custom-keybindings'))
        assert unrelated()==other_bindings
        subprocess.run([str(app),'on'],check=True,timeout=15)
        until(lambda: state().get('chats')==initial['chats'] and state().get('layout')=='bottom')
        assert state()['hotkeys']==initial['hotkeys']
        assert all(wm.get_value(key)==value for key,value in workspace_keys.items())
        print('PASS bottom persistence, shortcut cleanup/re-registration, workspace bindings preserved',flush=True)
    finally:
        if state().get('running'):
            for _ in range(3):
                if state().get('layout')==original:break
                step(1)
        call(session,iface,'Stop')


if __name__=='__main__':main()
