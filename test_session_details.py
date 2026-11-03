import unittest
from unittest.mock import Mock

from session_details import DetailsCard


class Surface:
    def __init__(self, x, y, width, height, mapped=True):
        self.x, self.y, self.width, self.height, self.mapped = x, y, width, height, mapped

    def winfo_rootx(self): return self.x
    def winfo_rooty(self): return self.y
    def winfo_width(self): return self.width
    def winfo_height(self): return self.height
    def winfo_ismapped(self): return self.mapped
    def withdraw(self): self.mapped = False


class PointerRoot:
    def __init__(self):
        self.point = (0, 0)
        self.jobs = {}
        self.clock = 0
        self.serial = 0

    def winfo_pointerxy(self): return self.point

    def after(self, delay, callback):
        self.serial += 1
        self.jobs[self.serial] = (self.clock + delay, callback)
        return self.serial

    def after_cancel(self, ident): self.jobs.pop(ident, None)

    def advance(self, elapsed):
        end = self.clock + elapsed
        while self.jobs:
            ident = min(self.jobs, key=lambda key: self.jobs[key][0])
            due, callback = self.jobs[ident]
            if due > end:
                break
            self.jobs.pop(ident)
            self.clock = due
            callback()
        self.clock = end


class PointerReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.card = DetailsCard.__new__(DetailsCard)
        self.card.root = PointerRoot()
        self.owner = Surface(100, 100, 178, 152)
        self.card.entries = {'a': {'window': self.owner, 'drag': {}}}
        self.card.window = Surface(100, 270, 382, 400, mapped=False)
        self.card.ident = self.card.target = self.card.pending = self.card.leave_pending = None
        self.card.pinned = False

    def test_reflow_under_stationary_pointer_opens_once_after_hover_delay(self):
        self.card.root.point = (50, 150)
        self.card.show = Mock()
        self.card.reconcile_pointer()
        self.assertFalse(self.card.root.jobs)
        self.owner.x = 20
        self.card.reconcile_pointer()
        self.card.root.advance(200)
        self.card.reconcile_pointer()
        self.card.root.advance(249)
        self.card.show.assert_not_called()
        self.card.root.advance(1)
        self.card.show.assert_called_once_with('a')

    def test_missed_leave_event_dismisses_without_restarting_grace(self):
        self.card.ident = 'a'
        self.card.window.mapped = True
        self.card.reconcile_pointer()
        self.card.root.advance(200)
        self.card.reconcile_pointer()
        self.card.root.advance(50)
        self.assertIsNone(self.card.ident)
        self.assertFalse(self.card.window.mapped)

    def test_pinned_card_survives_pointer_leave_and_reflow(self):
        self.card.ident, self.card.pinned = 'a', True
        self.card.reconcile_pointer()
        self.card.root.advance(1000)
        self.assertEqual(self.card.ident, 'a')
        self.assertFalse(self.card.root.jobs)

    def test_entering_card_cancels_dismissal_and_drag_prevents_new_hover(self):
        self.card.ident = 'a'
        self.card.window.mapped = True
        self.card.leave()
        self.card.root.point = (120, 300)
        self.card.reconcile_pointer()
        self.card.root.advance(1000)
        self.assertEqual(self.card.ident, 'a')
        self.card.hide()
        self.card.root.point = (120, 120)
        self.card.entries['a']['drag'] = {'x': 10, 'y': 10}
        self.card.reconcile_pointer()
        self.assertFalse(self.card.root.jobs)

    def test_delayed_show_is_rejected_after_pointer_moves_away(self):
        self.card.refresh = Mock()
        self.card.show('a')
        self.assertIsNone(self.card.ident)
        self.card.refresh.assert_not_called()


if __name__ == '__main__':
    unittest.main()
