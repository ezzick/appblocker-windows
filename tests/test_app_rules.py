"""
Тесты правил приложений и фильтров (AppRules).
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.blocker_utils import AppRule


class TestAppRule(unittest.TestCase):
    """Набор тестов для проверки правил сопоставления окон и процессов."""

    def test_rule_creation(self):
        """Проверка корректности создания объекта AppRule."""
        rule = AppRule(
            name="Telegram",
            process_names=["Telegram.exe"],
            title_whitelist=["Work Chat"],
            title_blacklist=["Settings"]
        )
        self.assertEqual(rule.name, "Telegram")
        self.assertEqual(rule.process_names, ["Telegram.exe"])
        self.assertEqual(rule.title_whitelist, ["Work Chat"])
        self.assertEqual(rule.title_blacklist, ["Settings"])

    def test_rule_defaults(self):
        """Проверка значений по умолчанию в AppRule."""
        rule = AppRule(name="Browser")
        self.assertEqual(rule.action, "close_window")
        self.assertEqual(rule.process_names, [])
        self.assertEqual(rule.exact_classes, [])
        self.assertEqual(rule.title_whitelist, [])
        self.assertEqual(rule.title_blacklist, [])

    def test_rule_action_types(self):
        """Проверка допустимости различных действий правила."""
        rule_close = AppRule(name="Test1", action="close_window")
        rule_tab = AppRule(name="Test2", action="close_tab")
        rule_min = AppRule(name="Test3", action="minimize_window")
        self.assertEqual(rule_close.action, "close_window")
        self.assertEqual(rule_tab.action, "close_tab")
        self.assertEqual(rule_min.action, "minimize_window")


def run_tests() -> bool:
    """Точка входа для запуска тестов модуля."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAppRule)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
