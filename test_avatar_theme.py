import json
from pathlib import Path
import tempfile
import unittest

from avatar_theme import ThemeSettings, luminance, palettes, read_config, write_config


class ThemeTests(unittest.TestCase):
    def test_dark_defaults_and_automatic_readable_text(self):
        for theme in palettes({}).values():
            self.assertLess(luminance(theme['background']), .06)
            contrast = (luminance(theme['foreground']) + .05) / (luminance(theme['background']) + .05)
            self.assertGreater(contrast, 7)
        self.assertEqual(palettes({'codex': {'background': '#ffffff'}})['codex']['foreground'], '#17202b')

    def test_reload_retains_valid_theme_then_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'themes.json'
            settings = ThemeSettings(path)
            write_config(path, {'codex': {'background': '#112233', 'foreground': '#abcdef'}})
            self.assertTrue(settings.reload())
            expected = settings.get('codex')
            for invalid in ('{', '{"codex":{"background":"invalid"}}', '[]', '{"claud":{}}'):
                path.write_text(invalid, encoding='utf-8')
                self.assertFalse(settings.reload(force=True))
                self.assertIsNotNone(settings.error)
                self.assertEqual(settings.get('codex'), expected)
            write_config(path, {'claude': {'background': '#35251d'}})
            self.assertTrue(settings.reload())
            self.assertIsNone(settings.error)
            self.assertEqual(settings.get('claude')['background'], '#35251d')
            self.assertFalse(settings.reload())
            path.unlink()
            self.assertTrue(settings.reload())
            self.assertEqual(settings.themes, palettes({}))

    def test_invalid_write_preserves_file_and_bom_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'themes.json'
            config = {'claude': {'background': '#AABBCC'}}
            path.write_text(json.dumps(config), encoding='utf-8-sig')
            self.assertEqual(read_config(path), config)
            for invalid in ({'claude': None}, {'codex': {'background': 'red'}}, {'codex': {'typo': '#123456'}}):
                with self.assertRaises(ValueError):
                    write_config(path, invalid)
                self.assertEqual(read_config(path), config)


if __name__ == '__main__':
    unittest.main()
