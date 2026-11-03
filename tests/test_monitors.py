"""
Тесты мониторинга процессов и окон Win32 (Monitors).
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.blocker_utils import (
    get_process_name,
    get_window_text,
    get_window_class,
    get_running_windows_list
)


class TestMonitors(unittest.TestCase):
    """Набор тестов для проверки системных функций мониторинга окон."""

    def test_get_running_windows_list(self):
        """Проверка получения списка запущенных окон."""
        windows = get_running_windows_list()
        self.assertIsInstance(windows, list)
        if windows:
            first = windows[0]
            self.assertIn("hwnd", first)
            self.assertIn("title", first)
            self.assertIn("process_name", first)
            self.assertIn("class_name", first)

    def test_query_functions_with_invalid_hwnd(self):
        """Проверка устойчивости функций к невалидным дескрипторам hwnd."""
        proc = get_process_name(0)
        self.assertEqual(proc, "")
        title = get_window_text(0)
        self.assertEqual(title, "")
        cls = get_window_class(0)
        self.assertEqual(cls, "")


def run_tests() -> bool:
    """Точка входа для запуска тестов модуля."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMonitors)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
