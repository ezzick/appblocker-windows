"""
test_config_manager.py - Автоматические unit-тесты для ConfigManager.
"""

import os
import sys
import json
import tempfile
import unittest

# Добавляем директорию src и родительскую в sys.path для импорта модулей AppBlocker
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
SRC_DIR = os.path.join(PARENT_DIR, "src")

for p in (SRC_DIR, PARENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from config_manager import ConfigManager, RuleConfig, PresetConfig, DEFAULT_RULES, DEFAULT_PRESETS


class TestConfigManager(unittest.TestCase):

    def setUp(self):
        # Создаем изолированный временный файл конфигурации для каждого теста
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.config_path = self.temp_file.name
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

    def tearDown(self):
        if os.path.exists(self.config_path):
            try:
                os.remove(self.config_path)
            except Exception:
                pass

    def test_default_config_creation(self):
        """Проверяет создание дефолтного конфига при отсутствии файла."""
        mgr = ConfigManager(config_path=self.config_path)
        self.assertTrue(os.path.exists(self.config_path))
        self.assertEqual(mgr.get_theme(), "dark")
        
        # Проверка наличия дефолтных правил
        rules = mgr.get_rules()
        self.assertGreaterEqual(len(rules), len(DEFAULT_RULES))
        telegram_rule = mgr.get_rule_by_id("telegram")
        self.assertIsNotNone(telegram_rule)
        self.assertEqual(telegram_rule.name, "Telegram")
        self.assertIn("Telegram.exe", telegram_rule.process_names)

        # Проверка канонического названия пресета ИИ
        ai_preset = mgr.get_preset_by_id("no_ai_50_10")
        self.assertIsNotNone(ai_preset)
        self.assertIn("Гигиена труда при работе с ИИ", ai_preset.name)
        self.assertEqual(ai_preset.allow_min, 50)
        self.assertEqual(ai_preset.block_min, 10)

    def test_add_and_update_rule(self):
        """Проверяет добавление и обновление правил."""
        mgr = ConfigManager(config_path=self.config_path)
        new_rule = RuleConfig(
            id="test_app",
            name="Тестовое приложение",
            enabled=True,
            process_names=["test.exe"],
            action="close_window"
        )
        mgr.add_or_update_rule(new_rule)

        # Проверяем в памяти и на диске
        found = mgr.get_rule_by_id("test_app")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Тестовое приложение")

        # Перезагружаем конфиг из файла
        reloaded_mgr = ConfigManager(config_path=self.config_path)
        found_reloaded = reloaded_mgr.get_rule_by_id("test_app")
        self.assertIsNotNone(found_reloaded)
        self.assertEqual(found_reloaded.process_names, ["test.exe"])

        # Обновляем правило
        new_rule.name = "Обновленное приложение"
        mgr.add_or_update_rule(new_rule)
        self.assertEqual(mgr.get_rule_by_id("test_app").name, "Обновленное приложение")

    def test_delete_rule(self):
        """Проверяет удаление правила по ID."""
        mgr = ConfigManager(config_path=self.config_path)
        rule = RuleConfig(id="to_delete", name="Удаляемое", process_names=["del.exe"])
        mgr.add_or_update_rule(rule)
        self.assertIsNotNone(mgr.get_rule_by_id("to_delete"))

        mgr.delete_rule("to_delete")
        self.assertIsNone(mgr.get_rule_by_id("to_delete"))

    def test_toggle_rule(self):
        """Проверяет включение/отключение правила."""
        mgr = ConfigManager(config_path=self.config_path)
        telegram_rule = mgr.get_rule_by_id("telegram")
        self.assertTrue(telegram_rule.enabled)

        mgr.toggle_rule("telegram", False)
        self.assertFalse(mgr.get_rule_by_id("telegram").enabled)

        mgr.toggle_rule("telegram", True)
        self.assertTrue(mgr.get_rule_by_id("telegram").enabled)

    def test_presets_crud(self):
        """Проверяет создание, чтение, обновление и удаление пресетов."""
        mgr = ConfigManager(config_path=self.config_path)
        new_preset = PresetConfig(
            id="custom_focus",
            name="⭐ Мой фокус 45/15",
            description="45 мин работы, 15 мин блок",
            allow_min=45,
            block_min=15,
            rule_ids=["telegram", "distractions"]
        )
        mgr.add_or_update_preset(new_preset)

        found = mgr.get_preset_by_id("custom_focus")
        self.assertIsNotNone(found)
        self.assertEqual(found.allow_min, 45)
        self.assertEqual(found.block_min, 15)
        self.assertEqual(found.rule_ids, ["telegram", "distractions"])

        # Удаление пресета
        mgr.delete_preset("custom_focus")
        self.assertIsNone(mgr.get_preset_by_id("custom_focus"))

    def test_user_modified_preset_preservation(self):
        """Проверяет, что отредактированные пользователем поля пресетов не затираются при повторном load()."""
        mgr = ConfigManager(config_path=self.config_path)
        ai_preset = mgr.get_preset_by_id("no_ai_50_10")
        self.assertIsNotNone(ai_preset)

        # Пользователь меняет название
        ai_preset.name = "Кастомное имя от пользователя"
        mgr.add_or_update_preset(ai_preset)

        # Перезагружаем менеджер
        mgr2 = ConfigManager(config_path=self.config_path)
        reloaded_preset = mgr2.get_preset_by_id("no_ai_50_10")
        self.assertEqual(reloaded_preset.name, "Кастомное имя от пользователя")

    def test_get_app_rules_for_ids(self):
        """Проверяет корректное преобразование RuleConfig в AppRule."""
        mgr = ConfigManager(config_path=self.config_path)
        app_rules = mgr.get_app_rules_for_ids(["telegram"])
        self.assertEqual(len(app_rules), 1)
        self.assertEqual(app_rules[0].name, "Telegram")
        self.assertIn("Telegram.exe", app_rules[0].process_names)


if __name__ == '__main__':
    unittest.main()
