"""Check real tiamos avatars against open elevated Kitty sessions on GNOME.

This deliberately double-clicks each avatar, focuses existing panes and restores
the initial pane/pointer. It never types in terminals or starts/stops agents.
Run as the desktop user with the installed tiamos monitor running.
"""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from elevated_sessions import ElevatedSessions
from kitty_bridge import request
from kitty_tabs import select_tab
from linux_desktop import bridge
from platform_runtime import state_directory


def main():
    from gi.repository import Gio, GLib
    def state(): return json.loads((state_directory()/'status.json').read_text())
    def wait(check):
        for _ in range(80):
            if check(): return
            time.sleep(.1)
        raise AssertionError('Expected desktop state did not appear')
    chats = ElevatedSessions().snapshot()
    assert len(chats) >= 2 and all(c['terminal']['kind']=='tab' and c['activity'].get('stats') for c in chats)
    original = next(r['id'] for r in request('snapshot')['windows'] if r['selected'])
    point = bridge().refresh(force=True)['pointer']
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    name = 'org.gnome.Mutter.RemoteDesktop'
    def call(path, iface, method, signature=None, values=()):
        return connection.call_sync(name,path,iface,method,
            GLib.Variant(signature,values) if signature else None,None,0,2000,None).unpack()
    remote = call('/org/gnome/Mutter/RemoteDesktop', name, 'CreateSession')[0]
    iface = name+'.Session'
    call(remote,iface,'Start')
    def motion(x,y):
        px,py=bridge().refresh(force=True)['pointer']
        call(remote,iface,'NotifyPointerMotionRelative','(dd)',(float(x-px),float(y-py)))
    try:
        for chat in chats:
            ident=chat['id'];pane=int(chat['terminal']['tab_id'].split(':')[1])
            other=next(c for c in chats if c['id']!=ident)
            select_tab(other['terminal']);wait(lambda:state()['selected']==other['id'])
            s=state();x,y=s['windows'][ident];w,h=s['sizes'][ident]
            motion(x+w//2,y+h//2);time.sleep(.03)
            for _ in range(2):
                call(remote,iface,'NotifyPointerButton','(ib)',(272,True))
                call(remote,iface,'NotifyPointerButton','(ib)',(272,False));time.sleep(.08)
            wait(lambda:state()['selected']==ident)
            assert next(r['id'] for r in request('snapshot')['windows'] if r['selected'])==pane
            assert state()['sizes'][ident]==[178,152] and not state()['focus_error']
            print('PASS real avatar double-click and exact Kitty pane:',pane)
        print(f'PASS {len(chats)} avatars with live activity and statistics')
    finally:
        request('focus',id=original);motion(*point);call(remote,iface,'Stop')


if __name__=='__main__':main()
