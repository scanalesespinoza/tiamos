"""Small synthesized chimes and bounded, live-only notification detection."""
from array import array
import io
import json
import math
from pathlib import Path
import sys
import time
import wave

NOTES = {
    'complete': (523.25, 659.25, 783.99),
    'attention': (659.25, 880.0, 659.25),
    'error': (392.0, 329.63),
    'level': (523.25, 659.25, 783.99, 1046.5),
}
PRIORITY = {'complete': 1, 'level': 2, 'error': 3, 'attention': 4}


def chime(kind, volume):
    """Short sine bells with smooth envelopes; volume affects only our PCM."""
    rate = 22050
    samples = array('h')
    length = int(rate * .16)
    gain = .22 * max(0, min(100, volume)) / 100
    for frequency in NOTES[kind]:
        for index in range(length):
            phase = index / (length - 1)
            envelope = math.sin(math.pi * phase) ** 2
            samples.append(round(32767 * gain * envelope * math.sin(2 * math.pi * frequency * index / rate)))
    if sys.byteorder != 'little':
        samples.byteswap()
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(samples.tobytes())
    return output.getvalue()


def windows_play(path):
    import winsound
    winsound.PlaySound(str(path) if path else None,
                      winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT if path else 0)


class Sounds:
    def __init__(self, directory, player=windows_play, clock=time.monotonic):
        self.directory = Path(directory)
        self.path = self.directory / 'sounds.json'
        self.player, self.clock = player, clock
        self.error = None
        try:
            config = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.enabled = config.get('enabled') if type(config.get('enabled')) is bool else True
        volume = config.get('volume', 25)
        self.volume = max(0, min(100, volume)) if type(volume) is int else 25
        self.cached = {}
        self.last_played = float('-inf')

    def status(self):
        return {'enabled': self.enabled, 'volume': self.volume, 'error': self.error}

    def configure(self, *, enabled=None, volume=None):
        config = {'enabled': self.enabled if enabled is None else bool(enabled),
                  'volume': self.volume if volume is None else max(0, min(100, int(volume)))}
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(config), encoding='utf-8')
            temporary.replace(self.path)
        except OSError:
            self.error = 'No se pudo guardar la configuración de sonido.'
            return
        self.stop()
        self.enabled, self.volume = config['enabled'], config['volume']

    def stop(self):
        try:
            self.player(None)
            self.error = None
        except (OSError, RuntimeError):
            self.error = 'Audio no disponible.'

    def play(self, kind, preview=False):
        if not self.enabled or not self.volume or kind not in NOTES:
            return False
        now = self.clock()
        if not preview and now - self.last_played < 3:
            return False
        try:
            path = self.directory / 'sounds' / (kind + '.wav')
            if self.cached.get(kind) != self.volume or not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(chime(kind, self.volume))
                self.cached[kind] = self.volume
            self.player(path)
            self.last_played = now
            self.error = None
            return True
        except (OSError, RuntimeError):
            self.error = 'No se pudo reproducir el sonido.'
            return False


class SoundEvents:
    """No prose, queue, or persisted history; first observation is always silent."""
    def __init__(self):
        self.sessions = {}

    def observe(self, chats, now):
        events = []
        present = set()
        for chat in chats:
            ident = chat['id']
            present.add(ident)
            activity = chat.get('activity') or {}
            previous = self.sessions.get(ident)
            error = max((action.get('at', 0) or 0 for action in activity.get('actions', [])
                         if action.get('outcome') == 'error'), default=0)
            current = {'since': previous['since'] if previous else now,
                       'complete': max(activity.get('last_completed_at') or 0, previous['complete'] if previous else 0),
                       'error': max(error, previous['error'] if previous else 0),
                       'attention': activity.get('phase') == 'Esperando intervención',
                       'level': max((activity.get('stats') or {}).get('level', 1), previous['level'] if previous else 1),
                       'updated': max(activity.get('updated_at') or 0, previous['updated'] if previous else 0),
                       'last_error_sound': previous['last_error_sound'] if previous else float('-inf')}
            self.sessions[ident] = current
            if previous is None:
                continue
            def fresh(stamp):
                return stamp >= current['since'] and 0 <= now - stamp < 60
            if current['attention'] and not previous['attention']:
                events.append('attention')
            if error > previous['error'] and fresh(error) and now - current['last_error_sound'] >= 20:
                events.append('error')
                current['last_error_sound'] = now
            if (current['complete'] > previous['complete'] and fresh(current['complete'])
                    and not activity.get('last_completion_error')):
                events.append('complete')
            if (current['level'] > previous['level'] and current['updated'] > previous['updated']
                    and fresh(current['updated'])):
                events.append('level')
        self.sessions = {key: value for key, value in self.sessions.items() if key in present}
        return max(events, key=PRIORITY.get) if events else None


class SoundMenu:
    def __init__(self, parent, sounds, quiet=lambda: False):
        import tkinter as tk
        self.sounds, self.quiet = sounds, quiet
        self.menu = tk.Menu(parent, tearoff=False)
        self.enabled = tk.BooleanVar(master=parent)
        self.volume = tk.IntVar(master=parent)

    def refresh(self):
        self.menu.delete(0, 'end')
        self.enabled.set(self.sounds.enabled)
        self.volume.set(self.sounds.volume)
        self.menu.add_checkbutton(label='Sonidos activados', variable=self.enabled,
                                 command=lambda: self.sounds.configure(enabled=self.enabled.get()))
        self.menu.add_separator()
        for level in (0, 10, 25, 50, 75, 100):
            self.menu.add_radiobutton(label=f'Volumen · {level} %', variable=self.volume, value=level,
                                     command=lambda: self.sounds.configure(volume=self.volume.get()))
        self.menu.add_separator()
        self.menu.add_command(label='Probar sonido', command=lambda: self.sounds.play('complete', preview=True),
                              state='normal' if self.sounds.enabled and self.sounds.volume and not self.quiet() else 'disabled')
        if self.quiet():
            self.menu.add_command(label='Pausados por modo tranquilo', state='disabled')
        if self.sounds.error:
            self.menu.add_command(label=self.sounds.error, state='disabled')
