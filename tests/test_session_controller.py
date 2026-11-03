"""
Тесты контроллера сессий и персистентности (SessionController).
"""
import os
import sys
import unittest
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.blocker_utils import (
    SessionState,
    SessionController,
    save_session_state,
    load_session_state,
    clear_session_state
)


class TestSessionController(unittest.TestCase):
    """Набор тестов для персистентности сессий и таймеров."""

    def test_save_and_load_session_state(self):
        """Проверка сохранения, чтения и очистки состояния сессии."""
        test_data = {
            "is_active": True,
            "session_type": "allow",
            "rule_name": "Telegram",
            "end_time": time.time() + 300,
            "target_hwnd": 0
        }
        save_session_state(test_data)
        loaded = load_session_state()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["rule_name"], "Telegram")
        self.assertTrue(loaded["is_active"])

        clear_session_state()
        cleared = load_session_state()
        self.assertIsNone(cleared)

    def test_session_state_constants(self):
        """Проверка констант состояний сессии SessionState."""
        self.assertEqual(SessionState.STOPPED, "STOPPED")
        self.assertEqual(SessionState.WORK_PHASE, "WORK_PHASE")
        self.assertEqual(SessionState.BLOCK_PHASE, "BLOCK_PHASE")

    def test_session_controller_init(self):
        """Проверка начальной инициализации и статуса SessionController."""
        controller = SessionController()
        self.assertFalse(controller.is_running())
        self.assertEqual(controller.state, SessionState.STOPPED)
        self.assertEqual(controller.get_seconds_remaining(), 0)
        status = controller.get_status()
        self.assertFalse(status["is_active"])
        self.assertEqual(status["state"], SessionState.STOPPED)


def run_tests() -> bool:
    """Точка входа для запуска тестов модуля."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSessionController)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
