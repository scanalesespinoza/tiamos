import os
import sys
import unittest
from unittest.mock import Mock

from avatar_paint import AvatarPaint
from avatar_layout import place_companion


class AvatarPaintTests(unittest.TestCase):
    def test_unchanged_frames_and_labels_do_not_repaint_but_theme_changes_do(self):
        label, picture = Mock(), Mock()
        paint = AvatarPaint(label=label, picture=picture)
        frame = object()
        for _ in range(20):
            paint.configure('label', text='Analizando', fg='#ffffff')
            paint.configure('picture', image=frame)
        label.configure.assert_called_once_with(text='Analizando', fg='#ffffff')
        picture.configure.assert_called_once_with(image=frame)
        paint.configure('label', fg='#111111')
        paint.configure('label', text='Analizando', fg='#ffffff')
        self.assertEqual(label.configure.call_count, 3)
        label.configure.assert_called_with(fg='#ffffff')
        paint.configure('picture', image=object())
        self.assertEqual(picture.configure.call_count, 2)

    def test_failed_native_write_is_retried(self):
        widget = Mock()
        widget.configure.side_effect = [RuntimeError('native error'), None]
        paint = AvatarPaint(label=widget)
        with self.assertRaises(RuntimeError):
            paint.configure('label', text='Ready')
        paint.configure('label', text='Ready')
        self.assertEqual(widget.configure.call_count, 2)

    def test_notice_placement_changes_only_with_visibility_or_size(self):
        badge = Mock()
        paint = AvatarPaint(badge=badge)
        for _ in range(20):
            paint.notice(True, True)
        self.assertEqual(badge.place.call_count, 1)
        paint.notice(True, False)
        badge.place.assert_called_with(relx=1, x=-3, y=0, anchor='ne')
        for _ in range(20):
            paint.notice(False, False)
        badge.place_forget.assert_called_once()

    def test_repeated_docking_does_not_move_native_window_but_resize_still_does(self):
        window = Mock()
        entry = dict(window=window, size=(178, 152))
        for _ in range(20):
            place_companion(entry, -300, 100)
        window.geometry.assert_called_once_with('178x152-300+100')
        entry['size'] = (89, 76)
        place_companion(entry, -300, 100)
        window.geometry.assert_called_with('89x76-300+100')
        self.assertEqual(window.geometry.call_count, 2)
        self.assertEqual(entry['position'], (-300, 100))

    @unittest.skipUnless(sys.platform in ('win32', 'darwin') or os.environ.get('DISPLAY'), 'Native desktop display')
    def test_native_label_and_visibility_remain_correct_across_updates(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        window = tk.Toplevel(root)
        label = tk.Label(window)
        label.pack()
        paint = AvatarPaint(window=window, label=label)
        try:
            paint.configure('label', text='Esperando', fg='#ffffff')
            paint.visible(False)
            paint.visible(False)
            self.assertEqual(window.state(), 'withdrawn')
            paint.configure('label', text='Revisando', fg='#112233')
            paint.visible(True)
            root.update_idletasks()
            self.assertEqual(label.cget('text'), 'Revisando')
            self.assertEqual(label.cget('fg'), '#112233')
            self.assertNotEqual(window.state(), 'withdrawn')
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
