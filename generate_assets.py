"""Render the app's code-native terminal icon into two small looping GIFs."""
from pathlib import Path
import math
from PIL import Image, ImageDraw


def generate(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    for state in ('working', 'sleeping'):
        frames = []
        for i in range(16):
            im = Image.new('RGB', (160, 104), '#171d28')
            d = ImageDraw.Draw(im)
            offset = round(math.sin(i * math.pi / 8) * (2 if state == 'working' else 1))
            accent = '#77e4c8' if state == 'working' else '#aab8d5'
            d.rounded_rectangle((27, 10 + offset, 133, 78 + offset), radius=12, fill='#2a3447', outline=accent, width=2)
            d.rounded_rectangle((35, 18 + offset, 125, 64 + offset), radius=7, fill='#0d1420')
            if state == 'working':
                for x in (59, 99):
                    d.rounded_rectangle((x, 30 + offset, x + 7, 41 + offset), radius=2, fill=accent)
                d.line((72, 48 + offset, 79, 51 + offset, 86, 48 + offset), fill=accent, width=2)
                for j in range(4):
                    x = 53 + j * 16
                    d.rounded_rectangle((x, 89, x + 10, 93), radius=2, fill=accent if j == (i // 2) % 4 else '#39465a')
                d.line((41, 53 + offset, 45, 56 + offset, 41, 59 + offset), fill=accent, width=2)
                if i % 8 < 5:
                    d.line((49, 59 + offset, 56, 59 + offset), fill=accent, width=2)
            else:
                for x in (57, 95):
                    d.arc((x, 28 + offset, x + 12, 40 + offset), 0, 180, fill=accent, width=2)
                d.ellipse((77, 47 + offset, 84, 54 + offset), outline=accent, width=2)
                for j in range(3):
                    x, y = 129 + j * 8, 27 - j * 8 - (i // 4) % 3
                    d.text((x, y), 'z', fill=accent)
            d.rounded_rectangle((64, 78 + offset, 96, 83 + offset), radius=2, fill='#46536b')
            frames.append(im)
        frames[0].save(destination / f'{state}.gif', save_all=True, append_images=frames[1:], duration=100 if state == 'working' else 180, loop=0)


if __name__ == '__main__':
    generate(Path(__file__).parent / 'assets')
