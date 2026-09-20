"""
test_app_rules.py - Автоматические unit-тесты для AppRule и логики сопоставления правил.
"""

import os
import sys
import unittest
from unittest.mock import patch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
SRC_DIR = os.path.join(PARENT_DIR, "src")

for p in (SRC_DIR, PARENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from blocker_utils import AppRule


class TestAppRule(unittest.TestCase):

    def test_rule_creation(self):
        """Проверяет корректное создание экземпляра AppRule с параметрами по умолчанию."""
        rule = AppRule(
            name="Telegram",
            process_names=["Telegram.exe"],
            class_pattern="Telegram",
            action="close_window"
        )
        self.assertEqual(rule.name, "Telegram")
        self.assertEqual(rule.process_names, ["Telegram.exe"])
        self.assertEqual(rule.action, "close_window")
        self.assertEqual(rule.exact_classes, [])
        self.assertEqual(rule.title_whitelist, [])
        self.assertEqual(rule.title_blacklist, [])

    @patch("blocker_utils.user32.IsWindowVisible", return_value=True)
    @patch("blocker_utils.get_window_text")
    @patch("blocker_utils.get_window_class")
    @patch("blocker_utils.get_process_name")
    def test_rule_matching_by_process_name(self, mock_proc, mock_cls, mock_text, mock_vis):
        """Проверяет срабатывание правила по имени процесса."""
        rule = AppRule(
            name="Telegram",
            process_names=["telegram.exe"],
            action="close_window"
        )

        mock_proc.return_value = "Telegram.exe"
        mock_cls.return_value = "Qt5QWindowIcon"
        mock_text.return_value = "Telegram (1 сообщение)"
        self.assertTrue(rule.matches(12345))

        # Другой процесс не должен совпадать
        mock_proc.return_value = "notepad.exe"
        self.assertFalse(rule.matches(12345))

    @patch("blocker_utils.user32.IsWindowVisible", return_value=True)
    @patch("blocker_utils.get_window_text")
    @patch("blocker_utils.get_window_class")
    @patch("blocker_utils.get_process_name")
    def test_rule_matching_with_blacklist(self, mock_proc, mock_cls, mock_text, mock_vis):
        """Проверяет фильтрацию по черному списку слов в заголовке вкладки/окна."""
        rule = AppRule(
            name="Соцсети",
            process_names=["chrome.exe", "msedge.exe"],
            title_blacklist=["YouTube", "VK", "Twitter"],
            action="close_tab"
        )

        mock_proc.return_value = "chrome.exe"
        mock_cls.return_value = "Chrome_WidgetWin_1"

        # Заголовок с YouTube попадает под блок
        mock_text.return_value = "YouTube - Музыка онлайн - Google Chrome"
        self.assertTrue(rule.matches(101))

        # Полезная вкладка не попадает под блок
        mock_text.return_value = "GitHub - Python Project - Google Chrome"
        self.assertFalse(rule.matches(101))

    @patch("blocker_utils.user32.IsWindowVisible", return_value=True)
    @patch("blocker_utils.get_window_text")
    @patch("blocker_utils.get_window_class")
    @patch("blocker_utils.get_process_name")
    def test_rule_matching_with_whitelist(self, mock_proc, mock_cls, mock_text, mock_vis):
        """Проверяет работу белого списка исключений."""
        rule = AppRule(
            name="Браузеры",
            process_names=["chrome.exe"],
            title_blacklist=["Google"],
            title_whitelist=["docs.google.com"],
            action="close_tab"
        )

        mock_proc.return_value = "chrome.exe"
        mock_cls.return_value = "Chrome_WidgetWin_1"

        # Общий Google - блокируется
        mock_text.return_value = "Поиск в Google"
        self.assertTrue(rule.matches(102))

        # Документ из белого списка - разрешен (не блокируется)
        mock_text.return_value = "Рабочий отчёт - docs.google.com"
        self.assertFalse(rule.matches(102))

    @patch("blocker_utils.user32.IsWindowVisible", return_value=False)
    def test_invisible_window_never_matches(self, mock_vis):
        """Невидимые окна никогда не должны попадать под правило."""
        rule = AppRule(name="Test", process_names=["test.exe"])
        self.assertFalse(rule.matches(999))


if __name__ == '__main__':
    unittest.main()
