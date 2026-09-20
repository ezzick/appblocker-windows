"""
test_session_controller.py - Автоматические unit-тесты для SessionController, состояний и путей к ресурсам.
"""

import os
import sys
import time
import unittest
from unittest.mock import patch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
SRC_DIR = os.path.join(PARENT_DIR, "src")

for p in (SRC_DIR, PARENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import blocker_utils
from blocker_utils import (
    SessionController,
    SessionState,
    get_resource_path,
    save_session_state,
    load_session_state,
    clear_session_state,
    AppRule
)


class TestSessionControllerAndUtils(unittest.TestCase):

    def setUp(self):
        clear_session_state()

    def tearDown(self):
        clear_session_state()

    def test_session_controller_initial_state(self):
        """Проверяет начальное состояние SessionController."""
        ctrl = SessionController()
        self.assertFalse(ctrl.is_running())
        self.assertEqual(ctrl.state, SessionState.STOPPED)
        st = ctrl.get_status()
        self.assertFalse(st["is_active"])
        self.assertEqual(st["remaining_sec"], 0)

    def test_session_controller_defaults(self):
        """Проверяет значения по умолчанию и константы состояний."""
        self.assertEqual(SessionState.IDLE, "idle")
        self.assertEqual(SessionState.WORK_PHASE, "work")
        self.assertEqual(SessionState.BLOCK_PHASE, "block")
        self.assertEqual(SessionState.STOPPED, "stopped")

    def test_session_state_persistence(self):
        """Проверяет сохранение, загрузку и очистку session_state.json."""
        state_data = {
            "session_name": "Тестовая сессия",
            "allow_min": 25,
            "block_min": 5,
            "rule_ids": ["telegram"],
            "allow_end_time": time.time() + 1500,
            "block_end_time": time.time() + 1800,
            "do_alert": True,
            "target_monitor": "auto"
        }
        save_session_state(state_data)

        loaded = load_session_state()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["session_name"], "Тестовая сессия")
        self.assertEqual(loaded["allow_min"], 25)
        self.assertEqual(loaded["block_min"], 5)
        self.assertEqual(loaded["rule_ids"], ["telegram"])

        clear_session_state()
        self.assertIsNone(load_session_state())

    def test_get_resource_path_standard(self):
        """Проверяет резолвинг путей в стандартном режиме (из исходного кода)."""
        if hasattr(sys, '_MEIPASS'):
            delattr(sys, '_MEIPASS')

        res_path = get_resource_path("assets/app_icon.ico")
        self.assertTrue(os.path.exists(res_path))
        self.assertTrue(res_path.endswith(os.path.normpath("assets/app_icon.ico")))

    def test_get_resource_path_frozen(self):
        """Проверяет работу get_resource_path в режиме PyInstaller _MEIPASS."""
        fake_meipass = r"C:\Users\AppData\Local\Temp\_MEI12345"
        with patch.object(sys, '_MEIPASS', fake_meipass, create=True):
            res_path = get_resource_path("assets/app_icon.ico")
            self.assertEqual(res_path, os.path.normpath(os.path.join(fake_meipass, "assets", "app_icon.ico")))


if __name__ == '__main__':
    unittest.main()
