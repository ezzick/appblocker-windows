"""
Тесты моделей конфигурации и пресетов (Config).
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.config_manager import RuleConfig, PresetConfig, DEFAULT_RULES, DEFAULT_PRESETS


class TestConfigModels(unittest.TestCase):
    """Набор тестов для проверки dataclass-моделей конфигурации."""

    def test_default_rules_exist(self):
        """Проверка наличия правил по умолчанию."""
        self.assertIsInstance(DEFAULT_RULES, list)
        self.assertGreater(len(DEFAULT_RULES), 0)
        telegram_rule = next((r for r in DEFAULT_RULES if r.id == "telegram"), None)
        self.assertIsNotNone(telegram_rule)
        self.assertEqual(telegram_rule.name, "Telegram")
        self.assertIsNone(telegram_rule.class_pattern)

    def test_version_constants(self):
        """Проверка констант версионирования в src.version."""
        from src.version import __version__, APP_VERSION, APP_TITLE, APP_NAME
        self.assertEqual(__version__, "2.1")
        self.assertEqual(APP_VERSION, "2.1")
        self.assertEqual(APP_NAME, "AppBlocker")
        self.assertIn("AppBlocker", APP_TITLE)
        self.assertIn("2.1", APP_TITLE)

    def test_default_presets_exist(self):
        """Проверка наличия пресетов по умолчанию."""
        self.assertIsInstance(DEFAULT_PRESETS, list)
        self.assertGreater(len(DEFAULT_PRESETS), 0)
        focus25 = next((p for p in DEFAULT_PRESETS if p.id == "focus_25"), None)
        self.assertIsNotNone(focus25)
        self.assertEqual(focus25.allow_min, 0)
        self.assertEqual(focus25.block_min, 25)

        no_ai = next((p for p in DEFAULT_PRESETS if p.id == "no_ai_50_10"), None)
        self.assertIsNotNone(no_ai)
        self.assertEqual(no_ai.allow_min, 50)
        self.assertEqual(no_ai.block_min, 10)

    def test_rule_config_creation(self):
        """Проверка создания и полей объекта RuleConfig."""
        rule = RuleConfig(
            id="browser",
            name="Браузер",
            enabled=True,
            process_names=["chrome.exe", "msedge.exe"]
        )
        self.assertEqual(rule.id, "browser")
        self.assertEqual(rule.name, "Браузер")
        self.assertTrue(rule.enabled)
        self.assertEqual(len(rule.process_names), 2)

    def test_preset_config_creation(self):
        """Проверка создания и полей объекта PresetConfig."""
        preset = PresetConfig(
            id="focus_25",
            name="Фокус 25 минут",
            description="25 мин работы, 5 мин отдыха",
            allow_min=25,
            block_min=5,
            rule_ids=["telegram", "browser"]
        )
        self.assertEqual(preset.id, "focus_25")
        self.assertEqual(preset.allow_min, 25)
        self.assertEqual(preset.block_min, 5)
        self.assertEqual(len(preset.rule_ids), 2)


def run_tests() -> bool:
    """Точка входа для запуска тестов модуля."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestConfigModels)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
