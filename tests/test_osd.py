"""
Тесты мониторов и рабочей области экрана (OSD).
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.blocker_utils import (
    get_target_monitor_work_area,
    RECT
)


class TestOSD(unittest.TestCase):
    """Набор тестов для проверки рабочей области мониторов Win32."""

    def test_target_monitor_work_area_returns_rect(self):
        """Проверка возврата структуры RECT для рабочей области монитора."""
        rect = get_target_monitor_work_area(target_mode="auto")
        self.assertIsInstance(rect, RECT)
        # Ширина и высота рабочей области монитора должны быть положительными
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)


def run_tests() -> bool:
    """Точка входа для запуска тестов модуля."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOSD)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
