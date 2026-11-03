import ctypes
import gc
import os
import unittest

from avatar_layout import monitor_work_area
from terminal_discovery import native_clients


@unittest.skipUnless(os.name == 'nt', 'Requires native Windows APIs')
class NativeResourceTests(unittest.TestCase):
    def assert_no_retained_polling_types(self, query):
        query()
        gc.collect()
        before = set(ctypes._pointer_type_cache)
        for _ in range(20):
            query()
        gc.collect()
        retained = [kind for kind in set(ctypes._pointer_type_cache) - before
            if getattr(kind, '__module__', '') in {'terminal_discovery', 'avatar_layout'}]
        self.assertEqual(retained, [], 'Polling created permanently cached ctypes structure types')

    def test_terminal_scan_reuses_native_structure_types(self):
        self.assert_no_retained_polling_types(native_clients)

    def test_monitor_query_reuses_native_structure_types(self):
        self.assert_no_retained_polling_types(lambda: monitor_work_area((0, 0)))


if __name__ == '__main__':
    unittest.main()
