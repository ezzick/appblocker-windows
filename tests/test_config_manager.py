"""
Тесты менеджера конфигурации (ConfigManager).
"""
import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.config_manager import ConfigManager, RuleConfig, PresetConfig


class TestConfigManager(unittest.TestCase):
    """Набор тестов для сохранения, загрузки и управления конфигурацией."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_config_manager_creation_and_defaults(self):
        """Проверка создания менеджера настроек и заполнения значениями по умолчанию."""
        cm = ConfigManager(config_path=self.config_path)
        rules = cm.get_rules()
        presets = cm.get_presets()
        self.assertGreater(len(rules), 0)
        self.assertGreater(len(presets), 0)

    def test_save_and_reload_settings(self):
        """Проверка сохранения настроек и их повторной загрузки из файла."""
        cm = ConfigManager(config_path=self.config_path)
        cm.set_theme("light")
        cm.set_show_floating_widget(True)
        cm.set_widget_position(250, 350)

        # Перезагружаем менеджер с тем же файлом
        cm2 = ConfigManager(config_path=self.config_path)
        self.assertEqual(cm2.get_theme(), "light")
        self.assertTrue(cm2.get_show_floating_widget())
        pos = cm2.get_widget_position()
        self.assertEqual(pos["x"], 250)
        self.assertEqual(pos["y"], 350)

    def test_add_and_delete_rule(self):
        """Проверка добавления и удаления правила."""
        cm = ConfigManager(config_path=self.config_path)
        new_rule = RuleConfig(
            id="custom_app",
            name="Пользовательское приложение",
            process_names=["custom.exe"]
        )
        cm.add_or_update_rule(new_rule)
        found = cm.get_rule_by_id("custom_app")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Пользовательское приложение")

        cm.delete_rule("custom_app")
        self.assertIsNone(cm.get_rule_by_id("custom_app"))


def run_tests() -> bool:
    """Точка входа для запуска тестов модуля."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestConfigManager)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
