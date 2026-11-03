"""Validated provider palettes with last-known-good live reload."""
import json
from pathlib import Path
import re
import tempfile

DEFAULTS = {
    'codex': {'background': '#24364b'},
    'claude': {'background': '#493326'},
}


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Los colores deben usar #RRGGBB.')
    return value.lower()


def luminance(value):
    channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))


def palettes(config):
    if not isinstance(config, dict) or set(config) - set(DEFAULTS):
        raise ValueError('El archivo debe contener solo codex y claude.')
    result = {}
    for provider, default in DEFAULTS.items():
        options = config.get(provider, {})
        if not isinstance(options, dict) or set(options) - {'background', 'foreground', 'notice'}:
            raise ValueError('Campos de tema admitidos: background, foreground, notice.')
        background = color(options.get('background', default['background']))
        dark = luminance(background) < .179
        result[provider] = {
            'name': 'Claude' if provider == 'claude' else 'Codex',
            'background': background,
            'foreground': color(options.get('foreground', '#f1f5f9' if dark else '#17202b')),
            'notice': color(options.get('notice', '#ffd18a' if dark else '#754000')),
        }
    return result


def read_config(path):
    try:
        if path.stat().st_size > 16384:
            raise ValueError('El archivo de temas supera 16 KiB.')
        config = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        config = {}
    palettes(config)
    return config


def write_config(path, config):
    palettes(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     suffix='.tmp', delete=False) as stream:
        temp = Path(stream.name)
        json.dump(config, stream, indent=2)
        stream.write('\n')
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class ThemeSettings:
    def __init__(self, path):
        self.path = path
        self.themes = palettes({})
        self.error = None
        self.signature = None
        self.reload(force=True)

    def reload(self, force=False):
        try:
            try:
                stat = self.path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
            except FileNotFoundError:
                signature = ('missing',)
            if not force and signature == self.signature:
                return False
            candidate = palettes(read_config(self.path))
            self.signature = signature
            self.error = None
            changed = candidate != self.themes
            self.themes = candidate
            return changed
        except (OSError, ValueError):
            self.error = 'No se pudo leer themes.json: revisa JSON, proveedores y colores #RRGGBB.'
            return False

    def get(self, provider):
        return dict(self.themes.get(provider, self.themes['codex']))
