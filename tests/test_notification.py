"""
Тесты звуковых уведомлений и тем оформления (Notification).
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.blocker_utils import (
    play_notification_sound,
    set_osd_theme,
    get_osd_theme
)


class TestNotification(unittest.TestCase):
    """Набор тестов для проверки звуковых оповещений и тем."""

    def test_theme_getter_and_setter(self):
        """Проверка переключения темы оформления OSD."""
        initial = get_osd_theme()
        set_osd_theme("light")
        self.assertEqual(get_osd_theme(), "light")
        set_osd_theme("dark")
        self.assertEqual(get_osd_theme(), "dark")
        set_osd_theme(initial)

    def test_sound_function_handles_unknown_type(self):
        """Проверка устойчивости функции play_notification_sound к неизвестным типам."""
        try:
            play_notification_sound("non_existent_sound_type")
        except Exception as e:
            self.fail(f"play_notification_sound raised exception: {e}")


def run_tests() -> bool:
    """Точка входа для запуска тестов модуля."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNotification)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
