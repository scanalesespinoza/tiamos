"""Small draggable Windows companions for today's local Codex conversations."""
from __future__ import annotations
import argparse
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import threading
import time

BASE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'CodexFloat'
CODEX = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def running():
    status = load_json(STATE / 'status.json', {})
    return status if time.time() - status.get('heartbeat', 0) < 8 else None


class Trace:
    """Incrementally inspect lifecycle metadata; do not retain message content."""
    END_EVENTS = {'task_complete', 'task_completed', 'turn_aborted', 'task_aborted', 'task_interrupted', 'turn_cancelled', 'session_end'}

    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0
        self.pending = b''
        self.active = set()
        self.last_activity = None

    def read(self):
        if self.path.stat().st_size < self.offset:
            self.offset, self.pending = 0, b''
            self.active.clear()
            self.last_activity = None
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            content = self.pending + stream.read()
            self.offset = stream.tell()
        lines = content.split(b'\n')
        self.pending = lines.pop()
        for line in lines:
            try:
                item = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if item.get('type') != 'event_msg':
                continue
            payload = item.get('payload', {})
            kind = payload.get('type')
            if kind not in {'task_started', 'user_message'} | self.END_EVENTS:
                continue
            try:
                stamp = dt.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')).astimezone()
            except (KeyError, ValueError):
                continue
            if self.last_activity is None or stamp > self.last_activity:
                self.last_activity = stamp
            turn = payload.get('turn_id') or payload.get('task_id')
            if kind == 'task_started':
                self.active.add(turn or 'current')
            elif kind in self.END_EVENTS:
                if turn:
                    self.active.discard(turn)
                    self.active.discard('current')
                else:
                    self.active.clear()


class Reader:
    def __init__(self, codex=CODEX):
        self.codex = codex
        self.traces = {}

    def snapshot(self, now=None):
        now = now or dt.datetime.now().astimezone()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        db = self.codex / 'state_5.sqlite'
        if not db.exists():
            raise RuntimeError('No se encuentra la base local de chats de Codex.')
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2)) as connection:
            rows = connection.execute('''SELECT id, title, rollout_path, source
                FROM threads WHERE archived=0 AND updated_at>=?
                AND attached_thread_parent_id IS NULL ORDER BY updated_at DESC''', (midnight,)).fetchall()
        result = []
        seen = set()
        for ident, title, path, source in rows:
            if 'subagent' in source.lower():
                continue
            seen.add(ident)
            if ident not in self.traces or self.traces[ident].path != Path(path):
                self.traces[ident] = Trace(path)
            trace = self.traces[ident]
            try:
                trace.read()
            except FileNotFoundError:
                continue
            # Actual turn activity, rather than a rename or metadata update.
            if trace.last_activity is None or trace.last_activity.date() != now.date():
                continue
            result.append({'id': ident, 'title': title or 'Chat de Codex', 'state': 'working' if trace.active else 'sleeping'})
        self.traces = {key: trace for key, trace in self.traces.items() if key in seen}
        return result


def serve():
    import tkinter as tk
    from PIL import Image, ImageTk, ImageSequence
    import ctypes
    import msvcrt
    # Keep Tk window coordinates aligned with physical pixels on scaled displays.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    STATE.mkdir(parents=True, exist_ok=True)
    lock = (STATE / 'instance.lock').open('a+b')
    lock.seek(0)
    lock.write(b'1')
    lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        return
    root = tk.Tk()
    root.withdraw()
    root.title('Codex Float')
    frames = {}
    for state in ('working', 'sleeping'):
        # Pillow composites GIF delta frames before Tk displays them.
        with Image.open(BASE / 'assets' / f'{state}.gif') as animation:
            frames[state] = [ImageTk.PhotoImage(frame.convert('RGBA')) for frame in ImageSequence.Iterator(animation)]
    positions_path = STATE / 'positions.json'
    positions = load_json(positions_path, {})
    widgets = {}
    updates = queue.Queue(maxsize=1)
    stop = threading.Event()
    reader = Reader()
    last_error = None

    def worker():
        while not stop.is_set():
            try:
                update = (reader.snapshot(), None)
            except Exception as error:
                update = (None, f'{type(error).__name__}: {error}')
            try:
                updates.get_nowait()
            except queue.Empty:
                pass
            updates.put(update)
            stop.wait(2)

    def bounds():
        user32 = ctypes.windll.user32
        return tuple(user32.GetSystemMetrics(index) for index in (76, 77, 78, 79))

    def clamp(x, y):
        left, top, width, height = bounds()
        return max(left, min(x, left + width - 178)), max(top, min(y, top + height - 152))

    def save_position(ident, window):
        positions[ident] = [window.winfo_x(), window.winfo_y()]
        atomic_json(positions_path, positions)

    def quit_all():
        stop.set()
        for ident, entry in widgets.items():
            save_position(ident, entry['window'])
        atomic_json(STATE / 'status.json', {'heartbeat': 0, 'running': False})
        root.destroy()

    def make_widget(chat):
        ident = chat['id']
        window = tk.Toplevel(root)
        window.title('Codex Float - ' + chat['title'])
        window.overrideredirect(True)
        window.attributes('-topmost', True)
        window.configure(bg='#171d28', highlightbackground='#46536b', highlightthickness=1)
        window.attributes('-alpha', .95)
        width, height = 178, 152
        _, _, screen_w, screen_h = bounds()
        index = len(widgets)
        location = positions.get(ident, [root.winfo_screenwidth() - 198 - (index // 5) * 190, 70 + (index % 5) * 164])
        x, y = clamp(int(location[0]), int(location[1]))
        window.geometry(f'{width}x{height}{x:+d}{y:+d}')
        title = tk.Label(window, text=chat['title'][:25], bg='#171d28', fg='#e4eaf4', font=('Segoe UI', 9), anchor='center')
        title.pack(fill='x', pady=(5, 0))
        picture = tk.Label(window, image=frames[chat['state']][0], bg='#171d28', borderwidth=0)
        picture.pack()
        label = tk.Label(window, bg='#171d28', fg='#77e4c8', font=('Segoe UI', 8))
        label.pack()
        entry = {'window': window, 'picture': picture, 'title': title, 'label': label, 'state': chat['state'], 'frame': 0}
        widgets[ident] = entry
        drag = {}

        def press(event):
            drag.update(x=event.x_root - window.winfo_x(), y=event.y_root - window.winfo_y())

        def move(event):
            if drag:
                x, y = clamp(event.x_root - drag['x'], event.y_root - drag['y'])
                window.geometry(f'{x:+d}{y:+d}')

        def release(event):
            save_position(ident, window)
            drag.clear()

        menu = tk.Menu(window, tearoff=False)
        menu.add_command(label='Apagar todos', command=quit_all)
        menu.add_command(label='Cerrar menu')
        for surface in (window, title, picture, label):
            surface.bind('<ButtonPress-1>', press)
            surface.bind('<B1-Motion>', move)
            surface.bind('<ButtonRelease-1>', release)
            surface.bind('<Button-3>', lambda event: menu.tk_popup(event.x_root, event.y_root))

    tick_number = 0

    def tick():
        nonlocal last_error, tick_number
        if (STATE / 'stop').exists():
            (STATE / 'stop').unlink(missing_ok=True)
            quit_all()
            return
        try:
            chats, error = updates.get_nowait()
            last_error = error
            if chats is not None:
                wanted = {chat['id'] for chat in chats}
                for ident in list(widgets):
                    if ident not in wanted:
                        save_position(ident, widgets[ident]['window'])
                        widgets.pop(ident)['window'].destroy()
                for chat in chats:
                    if chat['id'] not in widgets:
                        make_widget(chat)
                    entry = widgets[chat['id']]
                    if entry['state'] != chat['state']:
                        entry['frame'] = 0
                    entry['state'] = chat['state']
                    entry['title'].configure(text=chat['title'][:25])
                    entry['window'].title('Codex Float - ' + chat['title'])
        except queue.Empty:
            pass
        for entry in widgets.values():
            state = entry['state']
            if state == 'working' or tick_number % 2 == 0:
                entry['frame'] = (entry['frame'] + 1) % len(frames[state])
            entry['picture'].configure(image=frames[state][entry['frame']])
            entry['label'].configure(text='Sin conexion' if last_error else 'Trabajando' if state == 'working' else 'En descanso', fg='#e9bc79' if last_error else '#77e4c8' if state == 'working' else '#aab8d5')
        if tick_number % 10 == 0:
            atomic_json(STATE / 'status.json', {'running': True, 'heartbeat': time.time(), 'pid': os.getpid(), 'chats': len(widgets), 'working': sum(v['state'] == 'working' for v in widgets.values()), 'error': last_error, 'windows': {ident: [v['window'].winfo_x(), v['window'].winfo_y()] for ident, v in widgets.items()}})
        tick_number += 1
        root.after(100, tick)

    threading.Thread(target=worker, daemon=True).start()
    root.after(100, tick)
    try:
        root.mainloop()
    finally:
        stop.set()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description='Companeros flotantes de los chats de Codex activos hoy.')
    parser.add_argument('command', nargs='?', default='toggle', choices=['on', 'off', 'toggle', 'status', 'serve'])
    args = parser.parse_args()
    if args.command == 'serve':
        serve()
        return
    current = running()
    command = ('off' if current else 'on') if args.command == 'toggle' else args.command
    if command == 'status':
        print(json.dumps(current or {'running': False}, ensure_ascii=False, indent=2))
    elif command == 'off':
        if current:
            (STATE / 'stop').touch()
            for _ in range(40):
                if not running():
                    break
                time.sleep(.1)
            if running():
                raise SystemExit('No se pudo confirmar el apagado. Ejecuta codex-float status.')
        print('Codex Float apagado.')
    elif current:
        print('Codex Float ya esta encendido.')
    else:
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / 'stop').unlink(missing_ok=True)
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        with (STATE / 'app.log').open('a', encoding='utf-8') as log:
            subprocess.Popen([str(pythonw), str(BASE / 'codex_float.py'), 'serve'], cwd=BASE, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(60):
            if running():
                print('Codex Float encendido. Arrastra los terminales; clic derecho para apagar.')
                return
            time.sleep(.1)
        raise SystemExit(f'No se pudo iniciar. Revisa {STATE / "app.log"}')


if __name__ == '__main__':
    main()
