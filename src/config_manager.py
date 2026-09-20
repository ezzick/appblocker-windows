"""
Config Manager for AppBlocker
Управляет загрузкой, сохранением и дефолтными настройками приложения (JSON).
Поддерживает работу с правилами, пресетами, таймерами, темами оформления и автозагрузкой Windows.
Конфигурация хранится в %APPDATA%\\AppBlocker\\config.json для поддержки запуска из Program Files.
"""

import json
import logging
import os
import shutil
import sys
import winreg
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

from blocker_utils import AppRule, setup_logging, get_app_data_dir

logger = setup_logging("AppBlocker.Config")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(get_app_data_dir(), "config.json")


@dataclass
class RuleConfig:
    id: str
    name: str
    enabled: bool = True
    process_names: List[str] = field(default_factory=list)
    class_pattern: Optional[str] = None
    exact_classes: List[str] = field(default_factory=list)
    title_whitelist: List[str] = field(default_factory=list)
    title_blacklist: List[str] = field(default_factory=list)
    action: str = "close_window"  # "close_window", "close_tab"


@dataclass
class PresetConfig:
    id: str
    name: str
    description: str
    allow_min: int
    block_min: int
    rule_ids: List[str]


# ===== Дефолтные правила блокировок =====
DEFAULT_RULES: List[RuleConfig] = [
    RuleConfig(
        id="telegram",
        name="Telegram",
        enabled=True,
        process_names=["Telegram.exe"],
        class_pattern="Telegram",
        action="close_window"
    ),
    RuleConfig(
        id="distractions",
        name="Соцсети и видео (YouTube, VK и др.)",
        enabled=True,
        process_names=["chrome.exe", "firefox.exe", "msedge.exe", "opera.exe", "brave.exe", "yandex.exe"],
        title_blacklist=["YouTube", "ВКонтакте", "VK", "TikTok", "Instagram", "Reddit", "Twitter", "X.com", "Twitch", "Dzen"],
        action="close_tab"
    ),
    RuleConfig(
        id="ai_desktop",
        name="ИИ-программы (ChatGPT, Claude, Cursor, Windsurf и др.)",
        enabled=True,
        process_names=[
            "ChatGPT.exe", "Claude.exe", "Cursor.exe", "Windsurf.exe",
            "LM Studio.exe", "Jan.exe", "Ollama.exe", "Poe.exe",
            "Antigravity IDE.exe", "Antigravity.exe"
        ],
        action="minimize_window"
    ),
    RuleConfig(
        id="ai_web",
        name="ИИ-сайты (ChatGPT, Claude, Perplexity, DeepSeek и др.)",
        enabled=True,
        process_names=["chrome.exe", "firefox.exe", "msedge.exe", "opera.exe", "brave.exe", "yandex.exe"],
        title_blacklist=[
            "ChatGPT", "Claude", "Perplexity", "DeepSeek", "Gemini",
            "Poe", "Midjourney", "Kimi", "Grok", "OpenAI", "v0.dev", "Phind"
        ],
        action="close_tab"
    ),
    RuleConfig(
        id="discord",
        name="Discord",
        enabled=False,
        process_names=["Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe"],
        action="close_window"
    ),
    RuleConfig(
        id="games",
        name="Steam & Игры",
        enabled=False,
        process_names=["steam.exe", "EpicGamesLauncher.exe", "Battle.net.exe"],
        action="close_window"
    )
]

# ===== Дефолтные сценарии / пресеты =====
DEFAULT_PRESETS: List[PresetConfig] = [
    PresetConfig(
        id="no_ai_50_10",
        name="🧠 Гигиена труда при работе с ИИ (50 мин работа + 10 мин перерыв)",
        description="50 минут работы с ИИ-программами, затем 10 минут на осмысление",
        allow_min=50,
        block_min=10,
        rule_ids=["ai_desktop", "ai_web"]
    ),
    PresetConfig(
        id="deep_focus_50",
        name="🎯 50 мин без отвлечений",
        description="Мгновенный блок всех чатов и соцсетей на 50 минут (глубокий фокус)",
        allow_min=0,
        block_min=50,
        rule_ids=["telegram", "distractions"]
    ),
    PresetConfig(
        id="focus_25",
        name="☕ 25-минутный фокус",
        description="Быстрый спринт по методу Помидоро на 25 минут",
        allow_min=0,
        block_min=25,
        rule_ids=["telegram", "distractions"]
    ),
    PresetConfig(
        id="chats_work_25_5",
        name="💬 Клиентские чаты (25 мин работа + 5 мин отдых)",
        description="25 мин работы с чатами/видео, затем 5 мин перерыв на отдых и фокус",
        allow_min=25,
        block_min=5,
        rule_ids=["telegram", "distractions"]
    ),
    PresetConfig(
        id="hard_block_3h",
        name="🔒 Блокировка на 3 часа",
        description="Глубокая блокировка отвлекающих сервисов на 3 часа для сложной работы",
        allow_min=0,
        block_min=180,
        rule_ids=["telegram", "distractions"]
    ),
    PresetConfig(
        id="quick_check",
        name="⚡ Быстрая проверка чатов (5 мин работа + 10 мин фокус)",
        description="5 мин на ответы в чатах, затем 10 мин фокуса",
        allow_min=5,
        block_min=10,
        rule_ids=["telegram", "distractions"]
    )
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "1.0",
    "theme": "dark",
    "sound_enabled": True,
    "osd_enabled": True,
    "osd_duration_sec": 7,
    "target_monitor": "auto",  # "auto", "secondary", "primary"
    "window_geometry": None,
    "show_floating_widget": False,
    "widget_position": {"x": 100, "y": 100},
    "enable_peek_hotkey": True,
    "rules": [asdict(r) for r in DEFAULT_RULES],
    "presets": [asdict(p) for p in DEFAULT_PRESETS]
}


class ConfigManager:
    """Управляет загрузкой, сохранением и модификацией конфигурации AppBlocker."""

    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Загружает config.json из %APPDATA% (с авто-миграцией из SCRIPT_DIR) или создает дефолты."""
        if not os.path.exists(self.config_path):
            # Авто-миграция: если старый конфиг лежит в папке скриптов, копируем его в %APPDATA%
            old_config = os.path.join(SCRIPT_DIR, "config.json")
            if os.path.exists(old_config):
                try:
                    shutil.copy2(old_config, self.config_path)
                    logger.info(f"Мигрирован config.json из {old_config} в {self.config_path}")
                except Exception as ex:
                    logger.warning(f"Не удалось скопировать старый config.json: {ex}")

        if not os.path.exists(self.config_path):
            self.data = json.loads(json.dumps(DEFAULT_CONFIG))
            self.save()
            return self.data

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            # Дополняем отсутствующие ключи из дефолтов
            for k, v in DEFAULT_CONFIG.items():
                if k not in self.data:
                    self.data[k] = v

            # Дедупликация и миграция устаревших ID правил
            id_aliases_rules = {"steam": "games"}
            seen_rule_ids = set()
            clean_rules = []
            for r in self.data.get("rules", []):
                r_id = id_aliases_rules.get(r.get("id"), r.get("id"))
                r["id"] = r_id
                if r_id == "ai_desktop" and r.get("action") == "close_window":
                    r["action"] = "minimize_window"
                if r_id and r_id not in seen_rule_ids:
                    seen_rule_ids.add(r_id)
                    clean_rules.append(r)
            self.data["rules"] = clean_rules

            # Дедупликация и миграция устаревших ID пресетов
            id_aliases_presets = {
                "deep_focus": "deep_focus_50",
                "pomodoro": "focus_25",
                "client_work": "chats_work_25_5"
            }
            seen_preset_ids = set()
            clean_presets = []
            for p in self.data.get("presets", []):
                p_id = id_aliases_presets.get(p.get("id"), p.get("id"))
                p["id"] = p_id
                if p_id and p_id not in seen_preset_ids:
                    seen_preset_ids.add(p_id)
                    clean_presets.append(p)
            self.data["presets"] = clean_presets

            # Автоматически добавляем новые дефолтные правила, если их нет
            rules_added = False
            for default_rule in DEFAULT_RULES:
                if default_rule.id not in seen_rule_ids:
                    self.data["rules"].append(asdict(default_rule))
                    seen_rule_ids.add(default_rule.id)
                    rules_added = True

            # Автоматически добавляем новые дефолтные пресеты, если их нет
            presets_added = False
            for default_preset in DEFAULT_PRESETS:
                if default_preset.id not in seen_preset_ids:
                    self.data["presets"].append(asdict(default_preset))
                    seen_preset_ids.add(default_preset.id)
                    presets_added = True

            # Сохраняем обновленный конфиг при добавлении новых сущностей или миграциях
            self.save()

        except Exception as ex:
            logger.error(f"Error loading config from {self.config_path}: {ex}")
            self.data = json.loads(json.dumps(DEFAULT_CONFIG))
        return self.data

    def save(self):
        """Сохраняет текущий конфиг в config.json."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            logger.info(f"Config successfully saved to {self.config_path}")
        except Exception as ex:
            logger.error(f"Error saving config to {self.config_path}: {ex}")

    # ===== Работа с правилами =====

    def get_rules(self) -> List[RuleConfig]:
        rules_data = self.data.get("rules", [])
        return [RuleConfig(**r) for r in rules_data]

    def get_rule_by_id(self, rule_id: str) -> Optional[RuleConfig]:
        for r in self.get_rules():
            if r.id == rule_id:
                return r
        return None

    def get_app_rules_for_ids(self, rule_ids: Optional[List[str]] = None) -> List[AppRule]:
        """Преобразует список ID правил в объекты AppRule для движка блокировок."""
        app_rules = []
        rules = self.get_rules()
        for r in rules:
            if rule_ids is not None:
                if r.id in rule_ids:
                    app_rules.append(AppRule(
                        name=r.name,
                        process_names=r.process_names,
                        class_pattern=r.class_pattern,
                        exact_classes=r.exact_classes,
                        title_whitelist=r.title_whitelist,
                        title_blacklist=r.title_blacklist,
                        action=r.action
                    ))
            elif r.enabled:
                app_rules.append(AppRule(
                    name=r.name,
                    process_names=r.process_names,
                    class_pattern=r.class_pattern,
                    exact_classes=r.exact_classes,
                    title_whitelist=r.title_whitelist,
                    title_blacklist=r.title_blacklist,
                    action=r.action
                ))
        return app_rules

    def get_all_active_app_rules(self) -> List[AppRule]:
        """Возвращает все включенные AppRule."""
        return self.get_app_rules_for_ids(None)

    def add_or_update_rule(self, rule: RuleConfig):
        """Добавляет правило или обновляет существующее по ID."""
        rules = self.data.get("rules", [])
        updated = False
        for i, r in enumerate(rules):
            if r.get("id") == rule.id:
                rules[i] = asdict(rule)
                updated = True
                break
        if not updated:
            rules.append(asdict(rule))
        self.data["rules"] = rules
        self.save()

    def delete_rule(self, rule_id: str):
        """Удаляет правило по ID."""
        rules = self.data.get("rules", [])
        self.data["rules"] = [r for r in rules if r.get("id") != rule_id]
        self.save()

    def toggle_rule(self, rule_id: str, enabled: bool):
        """Включает или выключает правило."""
        rules = self.data.get("rules", [])
        for r in rules:
            if r.get("id") == rule_id:
                r["enabled"] = enabled
                break
        self.data["rules"] = rules
        self.save()

    # ===== Работа с пресетами =====

    def get_presets(self) -> List[PresetConfig]:
        presets_data = self.data.get("presets", [])
        return [PresetConfig(**p) for p in presets_data]

    def get_preset_by_id(self, preset_id: str) -> Optional[PresetConfig]:
        for p in self.get_presets():
            if p.id == preset_id:
                return p
        return None

    def add_or_update_preset(self, preset: PresetConfig):
        """Добавляет или обновляет пресет по ID."""
        presets = self.data.get("presets", [])
        updated = False
        for i, p in enumerate(presets):
            if p.get("id") == preset.id:
                presets[i] = asdict(preset)
                updated = True
                break
        if not updated:
            presets.append(asdict(preset))
        self.data["presets"] = presets
        self.save()

    def delete_preset(self, preset_id: str):
        """Удаляет пресет по ID."""
        presets = self.data.get("presets", [])
        self.data["presets"] = [p for p in presets if p.get("id") != preset_id]
        self.save()

    # ===== Общие настройки =====

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set_setting(self, key: str, value: Any):
        self.data[key] = value
        self.save()

    def get_theme(self) -> str:
        return self.get_setting("theme", "dark")

    def set_theme(self, theme: str):
        self.set_setting("theme", theme)

    def get_show_floating_widget(self) -> bool:
        return self.get_setting("show_floating_widget", False)

    def set_show_floating_widget(self, show: bool):
        self.set_setting("show_floating_widget", show)

    def get_widget_position(self) -> Dict[str, int]:
        return self.get_setting("widget_position", {"x": 100, "y": 100})

    def set_widget_position(self, x: int, y: int):
        self.set_setting("widget_position", {"x": int(x), "y": int(y)})

    def get_enable_peek_hotkey(self) -> bool:
        return self.get_setting("enable_peek_hotkey", True)

    def set_enable_peek_hotkey(self, enabled: bool):
        self.set_setting("enable_peek_hotkey", enabled)


# ===== Автозагрузка Windows (через HKCU) =====

AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_APP_NAME = "AppBlocker"


def is_autostart_enabled() -> bool:
    """Проверяет, включен ли автозапуск AppBlocker в реестре Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, AUTOSTART_APP_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as ex:
        logger.debug(f"Error checking autostart: {ex}")
        return False


def set_autostart(enabled: bool) -> bool:
    """Включает или выключает автозапуск AppBlocker при входе в Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                if getattr(sys, 'frozen', False):
                    cmd = f'"{sys.executable}"'
                else:
                    pyw_dir = os.path.dirname(sys.executable)
                    pyw_exe = os.path.join(pyw_dir, "pyw.exe")
                    if not os.path.exists(pyw_exe):
                        pyw_exe = os.path.join(pyw_dir, "pythonw.exe")
                    if not os.path.exists(pyw_exe):
                        pyw_exe = r"C:\WINDOWS\pyw.exe"
                    if not os.path.exists(pyw_exe):
                        pyw_exe = sys.executable

                    script = os.path.abspath(os.path.join(SCRIPT_DIR, "AppBlocker.pyw"))
                    cmd = f'"{pyw_exe}" "{script}"'

                winreg.SetValueEx(key, AUTOSTART_APP_NAME, 0, winreg.REG_SZ, cmd)
                logger.info(f"Autostart enabled in registry: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_APP_NAME)
                    logger.info("Autostart removed from registry.")
                except FileNotFoundError:
                    pass
            return True
    except Exception as ex:
        logger.error(f"Error setting autostart ({enabled}): {ex}")
        return False
