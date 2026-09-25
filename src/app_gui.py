"""
app_gui.py - Графический интерфейс для AppBlocker.

Цветовая палитра: Ezzick Coffee Theme for Obsidian (Dark & Light Coffee).
Поддержка сохранения активных сессий (Persistent Sessions) и библиотеки пользовательских пресетов.
"""

import sys
import os
import time
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Optional, Dict, Any, Callable

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from config_manager import ConfigManager, RuleConfig, PresetConfig, is_autostart_enabled, set_autostart
from blocker_utils import (
    session_controller,
    SessionState,
    get_running_windows_list,
    show_osd_notification,
    show_quick_peek,
    GlobalHotkeyListener,
    set_osd_theme,
    setup_logging,
    WindowsTrayIcon,
    get_resource_path
)

logger = setup_logging("AppBlocker.GUI")

# ===== Защита от запуска дубликатов (Single Instance Mutex) =====

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
WINDOW_TITLE = "AppBlocker - Управление фокусом"

_SINGLE_INSTANCE_MUTEX = None


def ensure_single_instance(cli_session_args=None):
    global _SINGLE_INSTANCE_MUTEX

    _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(None, True, "Local\\AppBlocker_SingleInstance_Mutex_v1")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        if cli_session_args:
            try:
                from blocker_utils import save_session_state, show_osd_notification
                from config_manager import ConfigManager
                cfg = ConfigManager()
                preset_id = getattr(cli_session_args, 'preset', None)
                allow_m = getattr(cli_session_args, 'allow_min', None)
                block_m = getattr(cli_session_args, 'block_min', None) or getattr(cli_session_args, 'pos_block_min', None)
                rule_ids = getattr(cli_session_args, 'rules', None)
                if rule_ids:
                    rule_ids = [r.strip() for r in rule_ids.split(",") if r.strip()]

                session_name = "Фокус-сессия (CLI)"
                if preset_id:
                    preset = cfg.get_preset_by_id(preset_id)
                    if preset:
                        allow_m = preset.allow_min
                        block_m = preset.block_min
                        rule_ids = preset.rule_ids
                        session_name = preset.name

                allow_m = int(allow_m or 0)
                block_m = int(block_m or 25)
                rule_ids = rule_ids or [r.id for r in cfg.get_rules() if r.enabled]

                now = time.time()
                allow_end = now + (allow_m * 60 if allow_m > 0 else 0)
                block_end = allow_end + (block_m * 60)
                state_data = {
                    "session_name": session_name,
                    "allow_min": allow_m,
                    "block_min": block_m,
                    "rule_ids": rule_ids,
                    "allow_end_time": allow_end,
                    "block_end_time": block_end,
                    "do_alert": True,
                    "target_monitor": cfg.get_setting("target_monitor", "auto"),
                    "created_at": now
                }
                save_session_state(state_data)
                show_osd_notification(
                    title="▶ Сессия запущена",
                    message=f"{session_name}\n{allow_m} мин работа ➔ {block_m} мин фокус",
                    duration_sec=4.0,
                    play_sound=True
                )
            except Exception as ex:
                logger.error(f"Error handling CLI session for running instance: {ex}")

        msg_id = user32.RegisterWindowMessageW("AppBlocker_Show_Instance")
        HWND_BROADCAST = 0xFFFF
        user32.PostMessageW(HWND_BROADCAST, msg_id, 0, 0)
        sys.exit(0)


# ===== Темы оформления (Ezzick Coffee Theme) =====

THEMES = {
    "dark": {
        "name": "☕ Dark Coffee (Тёмная)",
        "bg_main": "#161616",
        "bg_card": "#202020",
        "bg_card_hover": "#2a2a2a",
        "bg_input": "#1a1a1a",
        "fg_text": "#cfc0b0",
        "fg_muted": "#8d8070",
        "border": "#333130",
        "accent": "#c6b18b",
        "accent_fg": "#161616",
        "accent_hover": "#d5c3a3",
        "accent_orange": "#c2854b",
        "accent_green": "#7ba37a",
        "accent_red": "#b55a5a",
        "select_color": "#202020"
    },
    "light": {
        "name": "🥛 Light Coffee (Светлая)",
        "bg_main": "#ece0d1",
        "bg_card": "#dfd3c3",
        "bg_card_hover": "#d3c5b3",
        "bg_input": "#f4ede4",
        "fg_text": "#3c2f2f",
        "fg_muted": "#7a6b5d",
        "border": "#c8b9a6",
        "accent": "#967259",
        "accent_fg": "#ffffff",
        "accent_hover": "#85624b",
        "accent_orange": "#b36b2b",
        "accent_green": "#4a7c59",
        "accent_red": "#a74141",
        "select_color": "#dfd3c3"
    }
}


# ===== Диалоговое окно правила блокировки =====

class RuleDialog(tk.Toplevel):
    """Модальное окно добавления или редактирования правила блокировки."""

    def __init__(self, parent, theme: Dict[str, str], rule: Optional[RuleConfig] = None, on_save=None):
        super().__init__(parent)
        self.theme = theme
        self.rule = rule
        self.on_save = on_save

        self.title("Редактировать правило" if rule else "Добавить правило блокировки")
        self.geometry("540x630")
        self.minsize(480, 560)
        self.configure(bg=self.theme["bg_main"])
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        if rule:
            self._fill_data(rule)

    def _build_ui(self):
        pad_x = 16

        lbl_head = tk.Label(
            self, text="🛠️ Параметры правила блокировки",
            font=("Segoe UI", 12, "bold"),
            bg=self.theme["bg_main"], fg=self.theme["fg_text"]
        )
        lbl_head.pack(anchor="w", padx=pad_x, pady=(16, 12))

        # Быстрый выбор из запущенных окон
        lbl_pick = tk.Label(
            self, text="⚡ Быстрый выбор из запущенных окон:",
            font=("Segoe UI", 10, "bold"),
            bg=self.theme["bg_main"], fg=self.theme["accent"]
        )
        lbl_pick.pack(anchor="w", padx=pad_x, pady=(0, 4))

        self.running_windows = get_running_windows_list()
        combo_values = ["-- Выберите запущенную программу --"]
        for w in self.running_windows:
            title_short = (w['title'][:35] + '...') if len(w['title']) > 35 else w['title']
            combo_values.append(f"{w['process_name']}  |  {title_short}")

        self.combo_picker = ttk.Combobox(self, values=combo_values, state="readonly", font=("Segoe UI", 9))
        self.combo_picker.current(0)
        self.combo_picker.pack(fill="x", padx=pad_x, pady=(0, 14))
        self.combo_picker.bind("<<ComboboxSelected>>", self._on_window_picked)

        # Имя правила
        lbl_name = tk.Label(self, text="Название правила:", font=("Segoe UI", 10), bg=self.theme["bg_main"], fg=self.theme["fg_text"])
        lbl_name.pack(anchor="w", padx=pad_x, pady=(0, 2))
        self.entry_name = tk.Entry(
            self, font=("Segoe UI", 10),
            bg=self.theme["bg_input"], fg=self.theme["fg_text"],
            insertbackground=self.theme["fg_text"], relief="flat"
        )
        self.entry_name.pack(fill="x", padx=pad_x, pady=(0, 10), ipady=4)

        # Имя исполняемого файла (.exe)
        lbl_proc = tk.Label(self, text="Исполняемые файлы (.exe через запятую):", font=("Segoe UI", 10), bg=self.theme["bg_main"], fg=self.theme["fg_text"])
        lbl_proc.pack(anchor="w", padx=pad_x, pady=(0, 2))

        proc_frame = tk.Frame(self, bg=self.theme["bg_main"])
        proc_frame.pack(fill="x", padx=pad_x, pady=(0, 10))

        self.entry_proc = tk.Entry(
            proc_frame, font=("Segoe UI", 10),
            bg=self.theme["bg_input"], fg=self.theme["fg_text"],
            insertbackground=self.theme["fg_text"], relief="flat"
        )
        self.entry_proc.pack(side="left", fill="x", expand=True, ipady=4)

        btn_browse = tk.Button(
            proc_frame, text="Обзор...", font=("Segoe UI", 9),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"],
            relief="flat", cursor="hand2", command=self._on_browse_exe
        )
        btn_browse.pack(side="right", padx=(8, 0), ipadx=8, ipady=2)

        # Тип действия
        lbl_action = tk.Label(self, text="Тип блокировки:", font=("Segoe UI", 10), bg=self.theme["bg_main"], fg=self.theme["fg_text"])
        lbl_action.pack(anchor="w", padx=pad_x, pady=(0, 2))

        self.var_action = tk.StringVar(value="close_window")
        act_frame = tk.Frame(self, bg=self.theme["bg_main"])
        act_frame.pack(fill="x", padx=pad_x, pady=(0, 10))

        rb_win = tk.Radiobutton(
            act_frame, text="Закрывать всё окно программы (WM_CLOSE)", variable=self.var_action,
            value="close_window", bg=self.theme["bg_main"], fg=self.theme["fg_text"],
            selectcolor=self.theme["bg_card"], activebackground=self.theme["bg_main"],
            activeforeground=self.theme["fg_text"], font=("Segoe UI", 9)
        )
        rb_win.pack(anchor="w")

        rb_min = tk.Radiobutton(
            act_frame, text="Сворачивать и удерживать свёрнутым (без потери контекста/вкладок)", variable=self.var_action,
            value="minimize_window", bg=self.theme["bg_main"], fg=self.theme["fg_text"],
            selectcolor=self.theme["bg_card"], activebackground=self.theme["bg_main"],
            activeforeground=self.theme["fg_text"], font=("Segoe UI", 9)
        )
        rb_min.pack(anchor="w")

        rb_tab = tk.Radiobutton(
            act_frame, text="Закрывать только вкладку в браузере (Ctrl+W)", variable=self.var_action,
            value="close_tab", bg=self.theme["bg_main"], fg=self.theme["fg_text"],
            selectcolor=self.theme["bg_card"], activebackground=self.theme["bg_main"],
            activeforeground=self.theme["fg_text"], font=("Segoe UI", 9)
        )
        rb_tab.pack(anchor="w")

        # Черный список
        lbl_bl = tk.Label(self, text="Черный список слов / сайтов (через запятую):", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_main"], fg=self.theme["fg_text"])
        lbl_bl.pack(anchor="w", padx=pad_x, pady=(0, 1))

        lbl_bl_hint = tk.Label(
            self,
            text="💡 Закрывать при наличии этих слов в заголовке окна/вкладки (например: YouTube, VK, Twitter, TikTok, Dzen)",
            font=("Segoe UI", 8), bg=self.theme["bg_main"], fg=self.theme["fg_muted"], anchor="w", justify="left"
        )
        lbl_bl_hint.pack(fill="x", anchor="w", padx=pad_x, pady=(0, 4))

        self.entry_bl = tk.Entry(
            self, font=("Segoe UI", 10),
            bg=self.theme["bg_input"], fg=self.theme["fg_text"],
            insertbackground=self.theme["fg_text"], relief="flat"
        )
        self.entry_bl.pack(fill="x", padx=pad_x, pady=(0, 10), ipady=4)

        # Белый список
        lbl_wl = tk.Label(self, text="Белый список слов / исключений (не закрывать):", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_main"], fg=self.theme["fg_text"])
        lbl_wl.pack(anchor="w", padx=pad_x, pady=(0, 1))

        lbl_wl_hint = tk.Label(
            self,
            text="🛡️ Не закрывать вкладки и окна, содержащие эти слова (например: docs.google.com, notion, github, figma)",
            font=("Segoe UI", 8), bg=self.theme["bg_main"], fg=self.theme["fg_muted"], anchor="w", justify="left"
        )
        lbl_wl_hint.pack(fill="x", anchor="w", padx=pad_x, pady=(0, 4))

        self.entry_wl = tk.Entry(
            self, font=("Segoe UI", 10),
            bg=self.theme["bg_input"], fg=self.theme["fg_text"],
            insertbackground=self.theme["fg_text"], relief="flat"
        )
        self.entry_wl.pack(fill="x", padx=pad_x, pady=(0, 16), ipady=4)

        # Кнопки
        btn_frame = tk.Frame(self, bg=self.theme["bg_main"])
        btn_frame.pack(fill="x", padx=pad_x, pady=(0, 16))

        btn_cancel = tk.Button(
            btn_frame, text="Отмена", font=("Segoe UI", 10),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"],
            relief="flat", cursor="hand2", command=self.destroy
        )
        btn_cancel.pack(side="right", padx=(8, 0), ipadx=16, ipady=4)

        btn_ok = tk.Button(
            btn_frame, text="Сохранить", font=("Segoe UI", 10, "bold"),
            bg=self.theme["accent"], fg=self.theme["accent_fg"],
            relief="flat", cursor="hand2", command=self._save_and_close
        )
        btn_ok.pack(side="right", ipadx=18, ipady=4)

    def _add_process_to_entry(self, proc: str):
        if not proc:
            return
        curr = self.entry_proc.get().strip()
        if not curr:
            self.entry_proc.delete(0, tk.END)
            self.entry_proc.insert(0, proc)
        else:
            existing = [p.strip() for p in curr.split(",") if p.strip()]
            if not any(p.lower() == proc.lower() for p in existing):
                existing.append(proc)
                self.entry_proc.delete(0, tk.END)
                self.entry_proc.insert(0, ", ".join(existing))

    def _on_window_picked(self, event):
        idx = self.combo_picker.current()
        if idx > 0 and idx - 1 < len(self.running_windows):
            win = self.running_windows[idx - 1]
            proc = win['process_name']

            if not self.entry_name.get().strip():
                clean_name = os.path.splitext(proc)[0]
                self.entry_name.insert(0, clean_name.capitalize())

            self._add_process_to_entry(proc)
            self.combo_picker.current(0)

    def _on_browse_exe(self):
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Выберите исполняемый файл приложения",
            filetypes=[("Исполняемые файлы (*.exe)", "*.exe"), ("Все файлы (*.*)", "*.*")]
        )
        if file_path:
            exe_name = os.path.basename(file_path)
            self._add_process_to_entry(exe_name)
            if not self.entry_name.get().strip():
                self.entry_name.insert(0, os.path.splitext(exe_name)[0].capitalize())

    def _fill_data(self, rule: RuleConfig):
        self.entry_name.insert(0, rule.name)
        self.entry_proc.insert(0, ", ".join(rule.process_names))
        self.var_action.set(rule.action or "close_window")
        self.entry_bl.insert(0, ", ".join(rule.title_blacklist))
        self.entry_wl.insert(0, ", ".join(rule.title_whitelist))

    def _save_and_close(self):
        name = self.entry_name.get().strip()
        proc_str = self.entry_proc.get().strip()

        if not name:
            messagebox.showwarning("Внимание", "Укажите название правила!", parent=self)
            return

        procs = [p.strip() for p in proc_str.split(",") if p.strip()]
        blacklist = [b.strip() for b in self.entry_bl.get().split(",") if b.strip()]
        whitelist = [w.strip() for w in self.entry_wl.get().split(",") if w.strip()]

        rule_id = self.rule.id if self.rule else f"rule_{int(time.time())}"
        pattern = self.rule.class_pattern if self.rule else None

        updated_rule = RuleConfig(
            id=rule_id,
            name=name,
            enabled=self.rule.enabled if self.rule else True,
            process_names=procs,
            class_pattern=pattern,
            title_whitelist=whitelist,
            title_blacklist=blacklist,
            action=self.var_action.get()
        )

        if self.on_save:
            self.on_save(updated_rule)
        self.destroy()


# ===== Диалоговое окно пресета фокуса =====

class PresetDialog(tk.Toplevel):
    """Модальное окно создания и редактирования пресета фокуса."""

    def __init__(self, parent, theme: Dict[str, str], preset: Optional[PresetConfig] = None,
                 available_rules: Optional[List[RuleConfig]] = None,
                 on_save: Optional[Callable[[PresetConfig], None]] = None):
        super().__init__(parent)
        self.theme = theme
        self.preset = preset
        self.available_rules = available_rules or []
        self.on_save = on_save

        self.title("Редактировать пресет" if (preset and preset.id) else "Создать пресет фокуса")
        self.geometry("540x580")
        self.minsize(480, 500)
        self.configure(bg=self.theme["bg_main"])
        self.transient(parent)
        self.grab_set()

        self.rule_vars: Dict[str, tk.BooleanVar] = {}

        self._build_ui()
        if preset:
            self._fill_data(preset)

    def _build_ui(self):
        pad_x = 16

        lbl_head = tk.Label(
            self, text="🎯 Настройка пресета фокуса",
            font=("Segoe UI", 12, "bold"),
            bg=self.theme["bg_main"], fg=self.theme["fg_text"]
        )
        lbl_head.pack(anchor="w", padx=pad_x, pady=(14, 8))

        card = tk.Frame(
            self, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        card.pack(fill="both", expand=True, padx=pad_x, pady=(0, 12))

        # 1. Название
        lbl_name = tk.Label(card, text="Название пресета:", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"])
        lbl_name.pack(anchor="w", padx=14, pady=(10, 2))

        self.entry_name = tk.Entry(
            card, font=("Segoe UI", 10),
            bg=self.theme["bg_main"], fg=self.theme["fg_text"],
            insertbackground=self.theme["fg_text"], relief="flat", bd=4
        )
        self.entry_name.pack(fill="x", padx=14, pady=(0, 8))

        # 2. Описание
        lbl_desc = tk.Label(card, text="Краткое описание (опционально):", font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_muted"])
        lbl_desc.pack(anchor="w", padx=14, pady=(2, 2))

        self.entry_desc = tk.Entry(
            card, font=("Segoe UI", 9),
            bg=self.theme["bg_main"], fg=self.theme["fg_text"],
            insertbackground=self.theme["fg_text"], relief="flat", bd=4
        )
        self.entry_desc.pack(fill="x", padx=14, pady=(0, 10))

        # 3. Тайминги в ряд
        frame_times = tk.Frame(card, bg=self.theme["bg_card"])
        frame_times.pack(fill="x", padx=14, pady=(0, 12))

        # До блокировки (работа)
        box_allow = tk.Frame(frame_times, bg=self.theme["bg_card"])
        box_allow.pack(side="left", fill="x", expand=True, padx=(0, 8))

        lbl_allow = tk.Label(box_allow, text="До блокировки (мин):", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"])
        lbl_allow.pack(anchor="w")

        self.spin_allow = ttk.Spinbox(box_allow, from_=0, to=1440, width=8, font=("Segoe UI", 10))
        self.spin_allow.set(0)
        self.spin_allow.pack(anchor="w", pady=(2, 0))

        # Блокировка (фокус)
        box_block = tk.Frame(frame_times, bg=self.theme["bg_card"])
        box_block.pack(side="left", fill="x", expand=True, padx=(8, 0))

        lbl_block = tk.Label(box_block, text="Блокировка (мин):", font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"])
        lbl_block.pack(anchor="w")

        self.spin_block = ttk.Spinbox(box_block, from_=1, to=1440, width=8, font=("Segoe UI", 10))
        self.spin_block.set(25)
        self.spin_block.pack(anchor="w", pady=(2, 0))

        # 4. Чекбоксы правил
        lbl_rules_title = tk.Label(
            card, text="📋 Блокируемые приложения и правила в этом пресете:",
            font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"]
        )
        lbl_rules_title.pack(anchor="w", padx=14, pady=(4, 6))

        frame_rules_list = tk.Frame(card, bg=self.theme["bg_card"])
        frame_rules_list.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        frame_rules_list.columnconfigure(0, weight=1)
        frame_rules_list.columnconfigure(1, weight=1)

        for i, r in enumerate(self.available_rules):
            var = tk.BooleanVar(value=True)
            self.rule_vars[r.id] = var
            icon = "🌐" if r.action == "close_tab" else "📦"

            cb = tk.Checkbutton(
                frame_rules_list,
                text=f"{icon} {r.name}",
                variable=var,
                font=("Segoe UI", 9),
                bg=self.theme["bg_card"],
                fg=self.theme["fg_text"],
                selectcolor=self.theme["select_color"],
                activebackground=self.theme["bg_card"],
                activeforeground=self.theme["fg_text"],
                anchor="w"
            )
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=3)

        # 5. Кнопки сохранения и отмены
        btn_bar = tk.Frame(self, bg=self.theme["bg_main"])
        btn_bar.pack(fill="x", padx=pad_x, pady=(0, 14))

        btn_save = tk.Button(
            btn_bar, text="💾 Сохранить пресет", font=("Segoe UI", 10, "bold"),
            bg=self.theme["accent"], fg=self.theme["accent_fg"],
            relief="flat", cursor="hand2", command=self._save_and_close
        )
        btn_save.pack(side="right", padx=(8, 0), ipadx=12, ipady=4)

        btn_cancel = tk.Button(
            btn_bar, text="Отмена", font=("Segoe UI", 10),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"],
            relief="flat", cursor="hand2", command=self.destroy
        )
        btn_cancel.pack(side="right", ipadx=10, ipady=4)

    def _fill_data(self, preset: PresetConfig):
        self.entry_name.insert(0, preset.name)
        if preset.description:
            self.entry_desc.insert(0, preset.description)
        self.spin_allow.delete(0, tk.END)
        self.spin_allow.insert(0, str(preset.allow_min))
        self.spin_block.delete(0, tk.END)
        self.spin_block.insert(0, str(preset.block_min))

        for r_id, var in self.rule_vars.items():
            var.set(r_id in preset.rule_ids)

    def _save_and_close(self):
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("Внимание", "Укажите название пресета!", parent=self)
            return

        try:
            allow_min = max(0, int(self.spin_allow.get()))
            block_min = max(1, int(self.spin_block.get()))
        except Exception:
            messagebox.showwarning("Внимание", "Укажите корректные числовые значения минут!", parent=self)
            return

        selected_r_ids = [r_id for r_id, var in self.rule_vars.items() if var.get()]
        if not selected_r_ids:
            messagebox.showwarning("Внимание", "Выберите хотя бы одно правило блокировки для пресета!", parent=self)
            return

        preset_id = self.preset.id if (self.preset and self.preset.id) else f"preset_{int(time.time())}"
        desc = self.entry_desc.get().strip()
        if not desc:
            if allow_min > 0:
                desc = f"{allow_min} мин работы, затем {block_min} мин блокировки"
            else:
                desc = f"Блокировка на {block_min} мин"

        new_preset = PresetConfig(
            id=preset_id,
            name=name,
            description=desc,
            allow_min=allow_min,
            block_min=block_min,
            rule_ids=selected_r_ids
        )

        if self.on_save:
            self.on_save(new_preset)
        self.destroy()


# ===== Авто-скроллбар =====

class AutoScrollbar(ttk.Scrollbar):
    """Скроллбар, который автоматически скрывается, если контент помещается целиком."""
    def set(self, low, high):
        if float(low) <= 0.0 and float(high) >= 1.0:
            self.pack_forget()
        else:
            if not self.winfo_ismapped():
                self.pack(side="right", fill="y")
        super().set(low, high)


def _bind_mousewheel_to_canvas(canvas: tk.Canvas):
    """Обеспечивает плавную прокрутку колесиком мыши по Canvas."""
    def _on_wheel(event):
        try:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _bind_all(event):
        canvas.bind_all("<MouseWheel>", _on_wheel)

    def _unbind_all(event):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _bind_all)
    canvas.bind("<Leave>", _unbind_all)


# ===== Плавающий микро-виджет (Floating Pill) =====

class FloatingPillWidget(tk.Toplevel):
    """Компактный плавающий виджет поверх всех окон для быстрого подгляда времени."""

    def __init__(self, master, theme: Dict[str, str], config_manager: ConfigManager, on_open_main=None, on_toggle_session=None):
        super().__init__(master)
        self.theme = theme
        self.cfg = config_manager
        self.on_open_main = on_open_main
        self.on_toggle_session = on_toggle_session

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.92)
        except Exception:
            pass

        pos = self.cfg.get_widget_position()
        x = pos.get("x", 120)
        y = pos.get("y", 120)

        try:
            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            SM_CXVIRTUALSCREEN = 78
            SM_CYVIRTUALSCREEN = 79
            vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
            if x < vx or x > vx + vw - 60 or y < vy or y > vy + vh - 40:
                x, y = 120, 120
        except Exception:
            pass

        self.geometry(f"124x32+{x}+{y}")
        self.configure(bg=self.theme["border"])

        self.card = tk.Frame(self, bg=self.theme["bg_card"], cursor="fleur")
        self.card.pack(fill="both", expand=True, padx=1, pady=1)

        self.lbl_text = tk.Label(
            self.card, text="☕ AppBlocker",
            font=("Segoe UI", 9, "bold"),
            bg=self.theme["bg_card"], fg=self.theme["accent"],
            cursor="fleur"
        )
        self.lbl_text.pack(fill="both", expand=True, padx=4, pady=2)

        self._drag_start_x = 0
        self._drag_start_y = 0

        for w in (self.card, self.lbl_text):
            w.bind("<Button-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_motion)
            w.bind("<ButtonRelease-1>", self._on_drag_end)
            w.bind("<Double-Button-1>", self._on_double_click)
            w.bind("<Button-3>", self._show_context_menu)
            w.bind("<Enter>", lambda e: self._set_alpha(1.0))
            w.bind("<Leave>", lambda e: self._set_alpha(0.92))

    def _set_alpha(self, val: float):
        try:
            self.attributes("-alpha", val)
        except Exception:
            pass

    def _on_drag_start(self, event):
        """Запоминает точное смещение курсора относительно экрана (winfo_rootx/y) без скачков и крашей."""
        try:
            self._drag_offset_x = event.x_root - self.winfo_rootx()
            self._drag_offset_y = event.y_root - self.winfo_rooty()
        except Exception:
            self._drag_offset_x = getattr(event, 'x', 20)
            self._drag_offset_y = getattr(event, 'y', 15)

    def _on_drag_motion(self, event):
        if getattr(self, '_drag_offset_x', None) is not None and getattr(self, '_drag_offset_y', None) is not None:
            new_x = event.x_root - self._drag_offset_x
            new_y = event.y_root - self._drag_offset_y
            self.geometry(f"+{new_x}+{new_y}")

    def _on_drag_end(self, event):
        self._drag_offset_x = None
        self._drag_offset_y = None
        try:
            self.cfg.set_widget_position(self.winfo_x(), self.winfo_y())
        except Exception:
            pass

    def _on_double_click(self, event):
        if self.on_open_main:
            self.on_open_main()

    def _show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg=self.theme["bg_card"], fg=self.theme["fg_text"],
                       activebackground=self.theme["accent"], activeforeground=self.theme["accent_fg"],
                       font=("Segoe UI", 9))
        menu.add_command(label="⚡ Развернуть AppBlocker", command=self._on_double_click_action)
        if self.on_toggle_session:
            st = session_controller.get_status()
            is_active = st.get("is_active", False)
            if is_active:
                state = session_controller.state
                label_text = "⏹ Остановить этап «До блокировки»" if state == SessionState.WORK_PHASE else "⏹ Остановить блокировку"
            else:
                label_text = "▶ Запустить сессию"
            menu.add_command(label=label_text, command=self.on_toggle_session)
        menu.add_separator()
        menu.add_command(label="❌ Скрыть плавающий виджет", command=self.hide_widget)
        menu.post(event.x_root, event.y_root)

    def _on_double_click_action(self):
        if self.on_open_main:
            self.on_open_main()

    def hide_widget(self):
        self.cfg.set_show_floating_widget(False)
        self.withdraw()
        if hasattr(self.master, '_on_widget_visibility_changed'):
            self.master._on_widget_visibility_changed()

    def show_widget(self):
        self.cfg.set_show_floating_widget(True)
        self.deiconify()
        self.attributes("-topmost", True)
        if hasattr(self.master, '_on_widget_visibility_changed'):
            self.master._on_widget_visibility_changed()

    def update_timer(self, state: SessionState, sec_left: int, is_active: bool):
        if not is_active:
            self.lbl_text.config(text="☕ Ожидание", fg=self.theme["fg_muted"])
            return

        m, s = divmod(sec_left, 60)
        if state == SessionState.WORK_PHASE:
            self.lbl_text.config(text=f"⏳ {m:02d}:{s:02d}", fg=self.theme["accent_orange"])
        elif state == SessionState.BLOCK_PHASE:
            self.lbl_text.config(text=f"🔒 {m:02d}:{s:02d}", fg=self.theme["accent"])
        else:
            self.lbl_text.config(text="☕ 00:00", fg=self.theme["fg_muted"])

    def highlight_pulse(self):
        """Привлекает внимание к микро-виджету: выводит на передний план, подсвечивает рамкой и мигает."""
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()
        self.attributes("-alpha", 1.0)

        orig_text = self.lbl_text.cget("text")
        orig_fg = self.lbl_text.cget("fg")

        flash_steps = [
            ("#f59e0b", "#fffbeb", "🎯 ВОТ ОН!"),
            (self.theme["border"], self.theme["bg_card"], None),
            ("#f59e0b", "#fffbeb", "⏱️ AppBlocker"),
            (self.theme["border"], self.theme["bg_card"], None),
            ("#f59e0b", "#fffbeb", "✨ Виджет здесь"),
            (self.theme["border"], self.theme["bg_card"], None),
        ]

        def _step(idx):
            if not self.winfo_exists():
                return
            if idx < len(flash_steps):
                border_c, card_c, txt = flash_steps[idx]
                self.configure(bg=border_c)
                self.card.configure(bg=card_c)
                self.lbl_text.configure(bg=card_c)
                if txt:
                    is_light = "Light" in self.theme.get("name", "")
                    self.lbl_text.configure(text=txt, fg="#b45309" if is_light else "#fbbf24")
                else:
                    self.lbl_text.configure(text=orig_text, fg=orig_fg)
                self.after(320, lambda: _step(idx + 1))
            else:
                self.apply_theme(self.theme)
                self.attributes("-alpha", 0.92)

        _step(0)

    def apply_theme(self, theme: Dict[str, str]):
        self.theme = theme
        self.configure(bg=self.theme["border"])
        self.card.configure(bg=self.theme["bg_card"])
        self.lbl_text.configure(bg=self.theme["bg_card"])


class AppBlockerGUI(tk.Tk):
    """Главное окно приложения AppBlocker."""

    def __init__(
        self,
        start_preset_id: Optional[str] = None,
        allow_min: Optional[int] = None,
        block_min: Optional[int] = None,
        rule_ids: Optional[List[str]] = None,
        start_minimized: bool = False
    ):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.minsize(620, 560)

        self.cfg = ConfigManager()
        self.current_theme_key = self.cfg.get_theme()
        if self.current_theme_key not in THEMES:
            self.current_theme_key = "dark"
        self.theme = THEMES[self.current_theme_key]
        set_osd_theme(self.current_theme_key)

        self.configure(bg=self.theme["bg_main"])

        self.dashboard_rule_vars: Dict[str, tk.BooleanVar] = {}
        self.preset_buttons: Dict[str, tk.Button] = {}
        self.selected_preset_id: Optional[str] = None
        self.active_tab_index = 0

        self._apply_initial_geometry()
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)
        self.bind("<Unmap>", self._on_window_unmap)

        self._init_styles()
        self._build_main_ui()

        # Установка кастомной иконки приложения
        self.icon_path = get_resource_path(os.path.join("assets", "app_icon.ico"))
        if not os.path.exists(self.icon_path):
            self.icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(self.icon_path):
            try:
                self.iconbitmap(self.icon_path)
            except Exception:
                pass

        # Инициализация нативного системного трея Windows
        self.tray = WindowsTrayIcon(
            on_click=lambda: self.after(0, self._on_instance_signal_or_show),
            on_right_click=lambda: self.after(0, self._show_tray_context_menu),
            tooltip="AppBlocker - Управление фокусом",
            icon_path=self.icon_path if os.path.exists(self.icon_path) else None
        )
        self.tray.start()

        # Запуск сессии по CLI-параметрам или восстановление сохраненной
        if start_preset_id:
            preset = self.cfg.get_preset_by_id(start_preset_id)
            if preset:
                self._apply_preset_to_dashboard(preset)
                self.after(200, self._on_toggle_session)
        elif block_min is not None:
            a_m = allow_min if allow_min is not None else 0
            b_m = block_min
            r_ids = rule_ids or [r.id for r in self.cfg.get_rules() if r.enabled]
            self.spin_allow.delete(0, tk.END)
            self.spin_allow.insert(0, str(a_m))
            self.spin_block.delete(0, tk.END)
            self.spin_block.insert(0, str(b_m))
            for r_id, var in self.dashboard_rule_vars.items():
                var.set(r_id in r_ids)
            self._check_preset_match()
            self._update_summary_label()
            self.after(200, self._on_toggle_session)
        else:
            restored = session_controller.restore_if_active(self.cfg.get_app_rules_for_ids)
            if restored:
                allow_m = restored.get("allow_min", 0)
                block_m = restored.get("block_min", 50)
                r_ids = restored.get("rule_ids", [])

                self.spin_allow.delete(0, tk.END)
                self.spin_allow.insert(0, str(allow_m))

                self.spin_block.delete(0, tk.END)
                self.spin_block.insert(0, str(block_m))

                for r_id, var in self.dashboard_rule_vars.items():
                    var.set(r_id in r_ids)

                self._check_preset_match()
                self._update_summary_label()
            else:
                presets = self.cfg.get_presets()
                if presets:
                    self._apply_preset_to_dashboard(presets[0])

        if start_minimized:
            self.withdraw()

        # Инициализация плавающего виджета
        self.floating_widget: Optional[FloatingPillWidget] = None
        if self.cfg.get_show_floating_widget():
            self._init_floating_widget()
            self.floating_widget.show_widget()

        # Инициализация глобального хоткея быстрого подгляда (Win+Alt+T / Ctrl+Shift+B)
        self.hotkey_listener: Optional[GlobalHotkeyListener] = None
        if self.cfg.get_enable_peek_hotkey():
            self.hotkey_listener = GlobalHotkeyListener(callback=lambda: self.after(0, show_quick_peek))
            self.hotkey_listener.start()

        self._update_timer_loop()

    def _is_geometry_visible(self, geom_str: str) -> bool:
        """Проверяет, попадает ли заданная геометрия в пределы видимого экрана/мониторов."""
        if not geom_str:
            return False
        try:
            import re
            m = re.match(r'^(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$', str(geom_str).strip())
            if not m:
                return False
            w, h, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))

            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            SM_CXVIRTUALSCREEN = 78
            SM_CYVIRTUALSCREEN = 79

            vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

            if vw <= 0 or vh <= 0:
                vw = self.winfo_screenwidth()
                vh = self.winfo_screenheight()
                vx = 0
                vy = 0

            # Окно должно пересекаться с видимой областью мониторов минимум на 150x80 px
            if (x + w < vx + 150) or (x > vx + vw - 150):
                return False
            if (y + h < vy + 80) or (y > vy + vh - 80):
                return False
            if y < vy:
                return False
            return True
        except Exception:
            return False

    def _center_window(self):
        """Центрирует главное окно на основном мониторе."""
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w = 700
            h = min(840, max(600, sh - 100))
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _apply_initial_geometry(self):
        """Восстанавливает сохраненный размер и положение с обязательной проверкой видимости."""
        saved_geom = self.cfg.get_setting("window_geometry", None)
        if saved_geom and self._is_geometry_visible(saved_geom):
            try:
                self.geometry(saved_geom)
                return
            except Exception:
                pass

        self._center_window()

    def _ensure_floating_widget_visible(self):
        """Гарантирует, что плавающий виджет остаётся видимым при скрытии/сворачивании главного окна."""
        if hasattr(self, 'floating_widget') and self.floating_widget and self.floating_widget.winfo_exists():
            if self.cfg.get_show_floating_widget():
                self.floating_widget.deiconify()
                self.floating_widget.attributes("-topmost", True)
                self.floating_widget.lift()

    def _on_window_unmap(self, event):
        """Перехватывает стандартное нажатие кнопки [-] (свернуть) и убирает окно в трей."""
        if event.widget == self and self.state() == "iconic":
            self.withdraw()
            self._ensure_floating_widget_visible()

    def _on_close_window(self):
        """При нажатии на крестик сохраняет геометрию и сворачивает окно в системный трей."""
        try:
            geom = self.geometry()
            if self._is_geometry_visible(geom):
                self.cfg.set_setting("window_geometry", geom)
        except Exception:
            pass
        self.withdraw()
        self._ensure_floating_widget_visible()
        if not getattr(self, '_tray_balloon_shown', False):
            self._tray_balloon_shown = True
            if hasattr(self, 'tray') and self.tray:
                self.tray.show_balloon(
                    "AppBlocker свёрнут",
                    "Приложение продолжает работать в фоне. Кликните по иконке в трее, чтобы открыть окно."
                )

    def _on_instance_signal_or_show(self):
        """Вызывается при повторном запуске или клике по трею: обновляет сессию и показывает окно."""
        try:
            restored = session_controller.restore_if_active(self.cfg.get_app_rules_for_ids)
            if restored:
                allow_m = restored.get("allow_min", 0)
                block_m = restored.get("block_min", 50)
                r_ids = restored.get("rule_ids", [])
                self.spin_allow.delete(0, tk.END)
                self.spin_allow.insert(0, str(allow_m))
                self.spin_block.delete(0, tk.END)
                self.spin_block.insert(0, str(block_m))
                for r_id, var in self.dashboard_rule_vars.items():
                    var.set(r_id in r_ids)
                self._check_preset_match()
                self._update_summary_label()
        except Exception as ex:
            logger.debug(f"Error restoring on signal: {ex}")
        self.show_window()

    def show_window(self):
        """Восстанавливает окно из трея, центрирует при необходимости и выводит на передний план."""
        try:
            cur_geom = self.geometry()
            if not self._is_geometry_visible(cur_geom):
                self._center_window()
        except Exception:
            pass

        self.deiconify()
        self.state("normal")
        self.lift()
        self.attributes('-topmost', True)
        self.after_idle(self.attributes, '-topmost', False)
        self.focus_force()

    def really_quit(self):
        """Полное завершение работы приложения с сохранением настроек и удалением иконки из трея."""
        try:
            self.cfg.set_setting("window_geometry", self.geometry())
        except Exception:
            pass
        if hasattr(self, 'hotkey_listener') and self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        if hasattr(self, 'tray') and self.tray:
            self.tray.stop()
        if hasattr(self, 'floating_widget') and self.floating_widget and self.floating_widget.winfo_exists():
            try:
                self.floating_widget.destroy()
            except Exception:
                pass
        self.destroy()
        sys.exit(0)

    def _init_floating_widget(self):
        if not self.floating_widget or not self.floating_widget.winfo_exists():
            self.floating_widget = FloatingPillWidget(
                self, theme=self.theme, config_manager=self.cfg,
                on_open_main=self.show_window,
                on_toggle_session=self._on_toggle_session
            )

    def _on_toggle_floating_widget_from_ui(self):
        show = self.var_floating_widget.get()
        self.cfg.set_show_floating_widget(show)
        if show:
            self._init_floating_widget()
            self.floating_widget.show_widget()
        else:
            if self.floating_widget and self.floating_widget.winfo_exists():
                self.floating_widget.hide_widget()
        if hasattr(self, 'var_settings_floating_widget'):
            self.var_settings_floating_widget.set(show)

    def _on_widget_visibility_changed(self):
        show = self.cfg.get_show_floating_widget()
        if hasattr(self, 'var_floating_widget'):
            self.var_floating_widget.set(show)
        if hasattr(self, 'var_settings_floating_widget'):
            self.var_settings_floating_widget.set(show)

    def _show_tray_context_menu(self):
        """Отображает контекстное меню трея в позиции мыши."""
        menu = tk.Menu(
            self, tearoff=0,
            bg=self.theme["bg_card"],
            fg=self.theme["fg_text"],
            activebackground=self.theme["accent"],
            activeforeground=self.theme["accent_fg"],
            bd=1, relief="solid"
        )

        menu.add_command(
            label="⚡ Открыть AppBlocker",
            font=("Segoe UI", 9, "bold"),
            command=self.show_window
        )

        menu.add_command(
            label="📌 Скрыть мини-виджет" if self.cfg.get_show_floating_widget() else "📌 Показать мини-виджет",
            command=self._toggle_floating_widget_from_tray
        )

        menu.add_separator()

        if session_controller.is_running():
            state = session_controller.state
            stop_label = "⏹  Остановить этап «До блокировки»" if state == SessionState.WORK_PHASE else "⏹  Остановить блокировку"
            menu.add_command(
                label=stop_label,
                command=self._on_toggle_session
            )
        else:
            menu.add_command(
                label="▶  Запустить сессию",
                command=self._on_toggle_session
            )

        menu.add_separator()

        menu.add_command(
            label="❌ Выход из приложения",
            command=self.really_quit
        )

        try:
            cursor_pos = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor_pos))
            x, y = cursor_pos.x, cursor_pos.y
        except Exception:
            x, y = self.winfo_pointerxy()

        menu.tk_popup(x, y)

    def _toggle_floating_widget_from_tray(self):
        new_val = not self.cfg.get_show_floating_widget()
        self.cfg.set_show_floating_widget(new_val)
        if new_val:
            self._init_floating_widget()
            self.floating_widget.show_widget()
        else:
            if self.floating_widget and self.floating_widget.winfo_exists():
                self.floating_widget.hide_widget()
        self._on_widget_visibility_changed()

    def _init_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(
            "TNotebook",
            background=self.theme["bg_main"],
            borderwidth=0,
            tabmargins=[0, 0, 0, 0]
        )
        style.layout("TNotebook.Tab", [])

        style.configure(
            "Horizontal.TProgressbar",
            background=self.theme["accent"],
            troughcolor=self.theme["bg_card"],
            borderwidth=0
        )

    def _rebuild_all_ui(self):
        """Перестраивает весь интерфейс при смене темы оформления."""
        self.configure(bg=self.theme["bg_main"])
        self._init_styles()

        curr_allow = self.spin_allow.get() if hasattr(self, 'spin_allow') else "0"
        curr_block = self.spin_block.get() if hasattr(self, 'spin_block') else "50"
        checked_rules = [r_id for r_id, var in self.dashboard_rule_vars.items() if var.get()]

        for child in self.winfo_children():
            child.destroy()

        self.dashboard_rule_vars.clear()
        self.preset_buttons.clear()

        self._build_main_ui()

        if hasattr(self, 'spin_allow'):
            self.spin_allow.delete(0, tk.END)
            self.spin_allow.insert(0, curr_allow)
        if hasattr(self, 'spin_block'):
            self.spin_block.delete(0, tk.END)
            self.spin_block.insert(0, curr_block)

        for r_id in checked_rules:
            if r_id in self.dashboard_rule_vars:
                self.dashboard_rule_vars[r_id].set(True)

        self._switch_tab(self.active_tab_index)
        self._update_summary_label()
        self._refresh_preset_buttons()

    def _build_main_ui(self):
        header_frame = tk.Frame(self, bg=self.theme["bg_main"])
        header_frame.pack(fill="x", padx=16, pady=(12, 4))

        # Фирменная иконка Shield-Keyhole в заголовке
        self.header_icon_img = None
        icon_png_path = get_resource_path(os.path.join("assets", "app_icon_24.png"))
        if os.path.exists(icon_png_path):
            try:
                self.header_icon_img = tk.PhotoImage(file=icon_png_path)
            except Exception:
                self.header_icon_img = None

        if self.header_icon_img:
            lbl_icon = tk.Label(header_frame, image=self.header_icon_img, bg=self.theme["bg_main"])
            lbl_icon.pack(side="left", padx=(0, 8))

        lbl_logo = tk.Label(
            header_frame, text="AppBlocker" if self.header_icon_img else "🛡️ AppBlocker",
            font=("Segoe UI", 18, "bold"),
            bg=self.theme["bg_main"], fg=self.theme["fg_text"]
        )
        lbl_logo.pack(side="left")

        lbl_sub = tk.Label(
            header_frame, text="Focus & Time Control",
            font=("Segoe UI", 10),
            bg=self.theme["bg_main"], fg=self.theme["fg_muted"]
        )
        lbl_sub.pack(side="left", padx=(10, 0), pady=(4, 0))

        # Кастомная панель навигации
        nav_frame = tk.Frame(self, bg=self.theme["bg_main"])
        nav_frame.pack(fill="x", padx=16, pady=(4, 6))

        self.nav_buttons: List[tk.Button] = []
        tabs_meta = [
            ("⚡ Дашборд", 0),
            ("📚 Библиотека правил", 1),
            ("🎯 Пресеты", 2),
            ("⚙️ Настройки", 3)
        ]

        for title, idx in tabs_meta:
            btn = tk.Button(
                nav_frame, text=title, font=("Segoe UI", 9, "bold"),
                relief="flat", cursor="hand2", padx=16, pady=6, bd=0,
                command=lambda i=idx: self._switch_tab(i)
            )
            btn.pack(side="left", padx=(0, 4))
            self.nav_buttons.append(btn)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.tab_dashboard = tk.Frame(self.notebook, bg=self.theme["bg_main"])
        self.tab_rules = tk.Frame(self.notebook, bg=self.theme["bg_main"])
        self.tab_presets = tk.Frame(self.notebook, bg=self.theme["bg_main"])
        self.tab_settings = tk.Frame(self.notebook, bg=self.theme["bg_main"])

        self.notebook.add(self.tab_dashboard, text="")
        self.notebook.add(self.tab_rules, text="")
        self.notebook.add(self.tab_presets, text="")
        self.notebook.add(self.tab_settings, text="")

        self._build_dashboard_tab()
        self._build_rules_tab()
        self._build_presets_tab()
        self._build_settings_tab()

        self._switch_tab(self.active_tab_index)

    def _switch_tab(self, index: int):
        self.active_tab_index = index
        self.notebook.select(index)
        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.config(
                    bg=self.theme["accent"],
                    fg=self.theme["accent_fg"],
                    activebackground=self.theme["accent_hover"],
                    activeforeground=self.theme["accent_fg"]
                )
            else:
                btn.config(
                    bg=self.theme["bg_card"],
                    fg=self.theme["fg_text"],
                    activebackground=self.theme["bg_card_hover"],
                    activeforeground=self.theme["fg_text"]
                )

    # ===== 1. Вкладка Дашборд =====

    def _build_dashboard_tab(self):
        dash_container = tk.Frame(self.tab_dashboard, bg=self.theme["bg_main"])
        dash_container.pack(fill="both", expand=True)

        self.canvas_dash = tk.Canvas(dash_container, bg=self.theme["bg_main"], borderwidth=0, highlightthickness=0)
        self.scrollbar_dash = AutoScrollbar(dash_container, orient="vertical", command=self.canvas_dash.yview)
        self.dash_scrollable_frame = tk.Frame(self.canvas_dash, bg=self.theme["bg_main"])

        self.dash_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas_dash.configure(scrollregion=self.canvas_dash.bbox("all"))
        )

        self.canvas_dash_window = self.canvas_dash.create_window((0, 0), window=self.dash_scrollable_frame, anchor="nw")

        def _on_dash_canvas_configure(event):
            self.canvas_dash.itemconfig(self.canvas_dash_window, width=event.width)

        self.canvas_dash.bind("<Configure>", _on_dash_canvas_configure)
        self.canvas_dash.configure(yscrollcommand=self.scrollbar_dash.set)

        self.canvas_dash.pack(side="left", fill="both", expand=True)
        _bind_mousewheel_to_canvas(self.canvas_dash)

        # 1. Карточка статуса / таймера
        self.card_status = tk.Frame(
            self.dash_scrollable_frame, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        self.card_status.pack(fill="x", padx=8, pady=(4, 6))

        # Большие цифры таймера (лаконичный вид без дублирующих надписей)
        self.lbl_big_timer = tk.Label(
            self.card_status, text="00:00", font=("Segoe UI", 38, "bold"),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"]
        )
        self.lbl_big_timer.pack(anchor="center", pady=(12, 6))

        # Прогресс-бар
        self.progress_bar = ttk.Progressbar(
            self.card_status, style="Horizontal.TProgressbar", mode="determinate"
        )
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 10))

        # Главная кнопка запуска / остановки
        btn_box = tk.Frame(self.card_status, bg=self.theme["bg_card"])
        btn_box.pack(fill="x", padx=14, pady=(0, 10))

        self.btn_main_action = tk.Button(
            btn_box, text="▶  Запустить сессию", font=("Segoe UI", 11, "bold"),
            bg=self.theme["accent"], fg=self.theme["accent_fg"], relief="flat", cursor="hand2",
            command=self._on_toggle_session
        )
        self.btn_main_action.pack(fill="x", ipady=7)

        # Нижняя плашка карточки статуса: быстрый переключатель микро-виджета и хоткея
        widget_row = tk.Frame(self.card_status, bg=self.theme["bg_card"])
        widget_row.pack(fill="x", padx=14, pady=(0, 8))

        self.var_floating_widget = tk.BooleanVar(value=self.cfg.get_show_floating_widget())
        cb_float = tk.Checkbutton(
            widget_row, text="📌 Плавающий мини-виджет",
            variable=self.var_floating_widget, font=("Segoe UI", 8),
            bg=self.theme["bg_card"], fg=self.theme["fg_muted"],
            selectcolor=self.theme["select_color"], activebackground=self.theme["bg_card"],
            activeforeground=self.theme["fg_text"],
            command=self._on_toggle_floating_widget_from_ui
        )
        cb_float.pack(side="left")

        lbl_hotkey_hint = tk.Label(
            widget_row, text="⌨️ F9 / Ctrl+Shift+B — остаток времени",
            font=("Segoe UI", 8), bg=self.theme["bg_card"], fg=self.theme["fg_muted"]
        )
        lbl_hotkey_hint.pack(side="right")

        # 2. Карточка настройки сессии
        card_rules_pick = tk.Frame(
            self.dash_scrollable_frame, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        card_rules_pick.pack(fill="x", padx=8, pady=(2, 8))

        # Шапка карточки параметров с кнопкой сохранения в пресет
        header_params_frame = tk.Frame(card_rules_pick, bg=self.theme["bg_card"])
        header_params_frame.pack(fill="x", padx=14, pady=(8, 3))

        lbl_section_params = tk.Label(
            header_params_frame, text="⚙️ Параметры текущей сессии:",
            font=("Segoe UI", 10, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"]
        )
        lbl_section_params.pack(side="left")

        btn_save_curr_preset = tk.Button(
            header_params_frame,
            text="💾 Сохранить как пресет",
            font=("Segoe UI", 8, "bold"),
            bg=self.theme["bg_card_hover"], fg=self.theme["accent"],
            relief="flat", cursor="hand2", padx=8, pady=2,
            command=self._save_current_as_preset
        )
        btn_save_curr_preset.pack(side="right")

        # Динамическая сводка параметров (фиксированная высота 2 строки против скачков интерфейса)
        self.lbl_target_summary = tk.Label(
            card_rules_pick, text="🎯 Сценарий сессии...", font=("Segoe UI", 9, "bold"),
            bg=self.theme["bg_card"], fg=self.theme["accent_orange"],
            anchor="nw", justify="left", wraplength=580, height=2
        )
        self.lbl_target_summary.pack(fill="x", anchor="w", padx=14, pady=(0, 6))

        card_rules_pick.bind(
            "<Configure>",
            lambda e: self.lbl_target_summary.config(wraplength=max(200, e.width - 32)) if hasattr(self, 'lbl_target_summary') else None
        )

        self.lbl_pick_head = tk.Label(
            card_rules_pick, text="📋 Приложения для контроля (отметьте галочками):",
            font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_muted"]
        )
        self.lbl_pick_head.pack(anchor="w", padx=14, pady=(2, 4))

        self.frame_dash_checks = tk.Frame(card_rules_pick, bg=self.theme["bg_card"])
        self.frame_dash_checks.pack(fill="x", padx=14, pady=(0, 6))

        # Блок ручной настройки времени
        frame_time_spins = tk.Frame(card_rules_pick, bg=self.theme["bg_card"])
        frame_time_spins.pack(fill="x", padx=14, pady=(4, 10))

        # До блокировки (работа)
        row_allow = tk.Frame(frame_time_spins, bg=self.theme["bg_card"])
        row_allow.pack(anchor="w", pady=2)

        self.lbl_allow_title = tk.Label(
            row_allow, text="До блокировки:", font=("Segoe UI", 9),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"], width=15, anchor="w"
        )
        self.lbl_allow_title.pack(side="left")

        self.spin_allow = ttk.Spinbox(
            row_allow, from_=0, to=1440, width=6, font=("Segoe UI", 9),
            command=self._on_manual_param_change
        )
        self.spin_allow.set(0)
        self.spin_allow.pack(side="left", padx=(4, 6))
        self.spin_allow.bind("<KeyRelease>", lambda e: self._on_manual_param_change())

        lbl_unit_allow = tk.Label(row_allow, text="минут", font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_muted"])
        lbl_unit_allow.pack(side="left")

        # Время блокировки
        row_block = tk.Frame(frame_time_spins, bg=self.theme["bg_card"])
        row_block.pack(anchor="w", pady=2)

        self.lbl_block_title = tk.Label(
            row_block, text="Блокировка на:", font=("Segoe UI", 9),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"], width=15, anchor="w"
        )
        self.lbl_block_title.pack(side="left")

        self.spin_block = ttk.Spinbox(
            row_block, from_=1, to=1440, width=6, font=("Segoe UI", 9),
            command=self._on_manual_param_change
        )
        self.spin_block.set(50)
        self.spin_block.pack(side="left", padx=(4, 6))
        self.spin_block.bind("<KeyRelease>", lambda e: self._on_manual_param_change())

        lbl_unit_block = tk.Label(row_block, text="минут", font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_muted"])
        lbl_unit_block.pack(side="left")

        self._refresh_dashboard_checkboxes()

        # 3. Пресеты на Дашборде
        lbl_preset_head = tk.Label(
            self.dash_scrollable_frame,
            text="⚡ Готовые пресеты (клик для быстрой настройки):",
            font=("Segoe UI", 10, "bold"),
            bg=self.theme["bg_main"], fg=self.theme["fg_text"]
        )
        lbl_preset_head.pack(anchor="w", padx=8, pady=(6, 3))

        self.presets_frame = tk.Frame(self.dash_scrollable_frame, bg=self.theme["bg_main"])
        self.presets_frame.pack(fill="x", padx=8, pady=(0, 10))
        self._build_preset_buttons()

    def _build_preset_buttons(self):
        for w in self.presets_frame.winfo_children():
            w.destroy()
        self.preset_buttons.clear()

        presets = self.cfg.get_presets()
        for p in presets:
            btn_p = tk.Button(
                self.presets_frame, text=f"   {p.name}", font=("Segoe UI", 9),
                bg=self.theme["bg_card"], fg=self.theme["fg_text"],
                relief="flat", cursor="hand2", anchor="w", padx=10, pady=5,
                command=lambda preset=p: self._apply_preset_to_dashboard(preset)
            )
            btn_p.pack(fill="x", pady=2)
            self.preset_buttons[p.id] = btn_p

        self._refresh_preset_buttons()

    def _refresh_preset_buttons(self):
        if not self.preset_buttons and hasattr(self, 'presets_frame'):
            self._build_preset_buttons()
            return
        presets = {p.id: p for p in self.cfg.get_presets()}
        for p_id, btn in self.preset_buttons.items():
            preset = presets.get(p_id)
            if not preset:
                continue
            if p_id == self.selected_preset_id:
                btn.config(
                    text=f"●  {preset.name}",
                    bg=self.theme["bg_card_hover"],
                    fg=self.theme["accent"],
                    font=("Segoe UI", 9, "bold")
                )
            else:
                btn.config(
                    text=f"   {preset.name}",
                    bg=self.theme["bg_card"],
                    fg=self.theme["fg_text"],
                    font=("Segoe UI", 9)
                )

    def _refresh_dashboard_checkboxes(self):
        for widget in self.frame_dash_checks.winfo_children():
            widget.destroy()

        rules = self.cfg.get_rules()

        self.frame_dash_checks.columnconfigure(0, weight=1, minsize=180)
        self.frame_dash_checks.columnconfigure(1, weight=1, minsize=180)

        for i, r in enumerate(rules):
            if r.id not in self.dashboard_rule_vars:
                self.dashboard_rule_vars[r.id] = tk.BooleanVar(value=True)

            var = self.dashboard_rule_vars[r.id]
            icon = "🌐" if r.action == "close_tab" else "📦"

            row_idx = i // 2
            col_idx = i % 2

            cb = tk.Checkbutton(
                self.frame_dash_checks,
                text=f"{icon} {r.name}",
                variable=var,
                font=("Segoe UI", 9),
                bg=self.theme["bg_card"],
                fg=self.theme["fg_text"],
                selectcolor=self.theme["select_color"],
                activebackground=self.theme["bg_card"],
                activeforeground=self.theme["fg_text"],
                command=self._on_dashboard_rule_toggled,
                anchor="w"
            )
            cb.grid(row=row_idx, column=col_idx, sticky="w", padx=(0, 10), pady=2)

    def _on_dashboard_rule_toggled(self):
        self._check_preset_match()
        self._update_summary_label()

    def _on_manual_param_change(self):
        self._check_preset_match()
        self._update_summary_label()

    def _check_preset_match(self):
        if not hasattr(self, 'spin_allow') or not hasattr(self, 'spin_block'):
            return
        try:
            curr_allow = int(self.spin_allow.get())
            curr_block = int(self.spin_block.get())
        except Exception:
            curr_allow, curr_block = -1, -1

        curr_checked = set(r_id for r_id, v in self.dashboard_rule_vars.items() if v.get())

        matched_id = None
        for p in self.cfg.get_presets():
            if p.allow_min == curr_allow and p.block_min == curr_block and set(p.rule_ids) == curr_checked:
                matched_id = p.id
                break

        self.selected_preset_id = matched_id
        self._refresh_preset_buttons()

    def _apply_preset_to_dashboard(self, preset: PresetConfig):
        self.selected_preset_id = preset.id

        self.spin_allow.delete(0, tk.END)
        self.spin_allow.insert(0, str(preset.allow_min))

        self.spin_block.delete(0, tk.END)
        self.spin_block.insert(0, str(preset.block_min))

        for r_id, var in self.dashboard_rule_vars.items():
            var.set(r_id in preset.rule_ids)

        self._refresh_preset_buttons()
        self._update_summary_label()

    def _save_current_as_preset(self):
        try:
            allow_m = int(self.spin_allow.get())
            block_m = int(self.spin_block.get())
        except Exception:
            allow_m, block_m = 0, 25

        selected_r_ids = [r_id for r_id, var in self.dashboard_rule_vars.items() if var.get()]
        if not selected_r_ids:
            messagebox.showwarning("Внимание", "Отметьте хотя бы одно приложение галочкой перед сохранением пресета!", parent=self)
            return

        # Если в данный момент совпадает существующий пресет — открываем его на редактирование (перезапись)
        existing_preset = self.cfg.get_preset_by_id(self.selected_preset_id) if self.selected_preset_id else None
        if existing_preset:
            target_preset = PresetConfig(
                id=existing_preset.id,
                name=existing_preset.name,
                description=existing_preset.description,
                allow_min=allow_m,
                block_min=block_m,
                rule_ids=selected_r_ids
            )
        else:
            target_preset = PresetConfig(
                id="",
                name="⭐ Мой фокус-сценарий",
                description="",
                allow_min=allow_m,
                block_min=block_m,
                rule_ids=selected_r_ids
            )
        self._open_add_preset_dialog(initial_preset=target_preset)

    def _get_selected_app_rules(self) -> List[Any]:
        selected_ids = [r_id for r_id, var in self.dashboard_rule_vars.items() if var.get()]
        return self.cfg.get_app_rules_for_ids(selected_ids)

    def _update_summary_label(self):
        if not hasattr(self, 'spin_allow') or not hasattr(self, 'lbl_allow_title') or not hasattr(self, 'lbl_target_summary'):
            return
        try:
            allow_m = int(self.spin_allow.get())
            block_m = int(self.spin_block.get())
        except Exception:
            allow_m, block_m = 0, 0

        selected_rules = self._get_selected_app_rules()
        if not selected_rules:
            self.lbl_pick_head.config(text="📋 Выберите приложения для контроля в этой сессии:")
            self.lbl_target_summary.config(
                text="⚠️ Отметьте хотя бы одно приложение или сайт галочкой!",
                fg=self.theme["accent_red"]
            )
            if not session_controller.is_running():
                self.btn_main_action.config(text="▶  Отметьте приложения для запуска", state="disabled")
            return

        names = ", ".join([r.name for r in selected_rules])
        if not session_controller.is_running():
            self.btn_main_action.config(state="normal")

        self.lbl_allow_title.config(text="До блокировки:")
        self.lbl_block_title.config(text="Блокировка на:")

        if allow_m > 0:
            self.lbl_pick_head.config(
                text=f"📋 Приложения под контролем (доступны сейчас, закроются через {allow_m} мин):"
            )
            self.lbl_target_summary.config(
                text=f"⏳ Сначала {allow_m} мин. с приложениями ➔ затем {block_m} мин. блокировки для {names}",
                fg=self.theme["accent_orange"]
            )
            if not session_controller.is_running():
                self.btn_main_action.config(
                    text=f"▶  Через {allow_m} мин блокировать на {block_m} мин",
                    bg=self.theme["accent"],
                    fg=self.theme["accent_fg"]
                )
        else:
            self.lbl_pick_head.config(
                text="📋 Будут заблокированы сразу (отметьте галочками):"
            )
            self.lbl_target_summary.config(
                text=f"🔒 Блокировать на {block_m} мин: {names}",
                fg=self.theme["accent_orange"]
            )
            if not session_controller.is_running():
                self.btn_main_action.config(
                    text=f"▶  Запустить блокировку на {block_m} мин",
                    bg=self.theme["accent"],
                    fg=self.theme["accent_fg"]
                )

    def _on_toggle_session(self):
        if session_controller.is_running():
            session_controller.stop()
            self.btn_main_action.config(
                text="▶  Запустить сессию",
                bg=self.theme["accent"],
                fg=self.theme["accent_fg"]
            )
            self.lbl_big_timer.config(text="00:00", fg=self.theme["fg_text"])
            self.progress_bar['value'] = 0
            self._update_summary_label()
        else:
            try:
                allow_m = int(self.spin_allow.get())
                block_m = int(self.spin_block.get())
            except Exception:
                messagebox.showerror("Ошибка", "Укажите корректное время в минутах!", parent=self)
                return

            selected_ids = [r_id for r_id, var in self.dashboard_rule_vars.items() if var.get()]
            selected_rules = self.cfg.get_app_rules_for_ids(selected_ids)
            if not selected_rules:
                messagebox.showwarning("Внимание", "Не выбрано ни одно приложение для контроля!", parent=self)
                return

            session_controller.start_session(
                allow_min=allow_m,
                block_min=block_m,
                rules=selected_rules,
                rule_ids=selected_ids
            )
            btn_text = "⏹  Остановить этап «До блокировки»" if allow_m > 0 else "⏹  Остановить блокировку"
            self.btn_main_action.config(
                text=btn_text,
                bg=self.theme["accent_red"],
                fg="#ffffff"
            )

    def _update_timer_loop(self):
        state = session_controller.state
        sec_left = session_controller.get_seconds_remaining()

        if state == SessionState.IDLE or state == SessionState.STOPPED:
            if not session_controller.is_running() and self.btn_main_action['text'].startswith("⏹"):
                self.btn_main_action.config(
                    text="▶  Запустить сессию",
                    bg=self.theme["accent"],
                    fg=self.theme["accent_fg"]
                )
                self.lbl_big_timer.config(text="00:00", fg=self.theme["fg_text"])
                self.progress_bar['value'] = 0
                self._update_summary_label()
        else:
            m = sec_left // 60
            s = sec_left % 60
            self.lbl_big_timer.config(text=f"{m:02d}:{s:02d}")

            if state == SessionState.WORK_PHASE:
                self.lbl_big_timer.config(fg=self.theme["accent_orange"])

                tot = session_controller.total_phase_sec or (session_controller.allow_min * 60) or 1
                val = ((tot - sec_left) / max(1, tot)) * 100
                self.progress_bar['value'] = min(100, max(0, val))
                self.btn_main_action.config(
                    text="⏹  Остановить этап «До блокировки»",
                    bg=self.theme["accent_red"],
                    fg="#ffffff"
                )

            elif state == SessionState.BLOCK_PHASE:
                self.lbl_big_timer.config(fg=self.theme["accent"])

                tot = session_controller.total_phase_sec or (session_controller.block_min * 60) or 1
                val = ((tot - sec_left) / max(1, tot)) * 100
                self.progress_bar['value'] = min(100, max(0, val))
                self.btn_main_action.config(
                    text="⏹  Остановить блокировку",
                    bg=self.theme["accent_red"],
                    fg="#ffffff"
                )

        # Обновление динамического заголовка окна в панели задач (Taskbar Title)
        is_running = (state == SessionState.WORK_PHASE or state == SessionState.BLOCK_PHASE)
        if is_running:
            if state == SessionState.WORK_PHASE:
                self.title(f"⏳ {m:02d}:{s:02d} | До блокировки — AppBlocker")
            elif state == SessionState.BLOCK_PHASE:
                self.title(f"🔒 {m:02d}:{s:02d} | Блокировка — AppBlocker")
        else:
            self.title(WINDOW_TITLE)

        # Обновление подсказки трея
        if hasattr(self, 'tray') and self.tray:
            if state == SessionState.WORK_PHASE:
                self.tray.set_tooltip(f"AppBlocker: {m:02d}:{s:02d} (До блокировки)")
            elif state == SessionState.BLOCK_PHASE:
                self.tray.set_tooltip(f"AppBlocker: {m:02d}:{s:02d} (Блокировка)")
            else:
                self.tray.set_tooltip("AppBlocker — Ожидание сессии")

        # Обновление плавающего микро-виджета
        if hasattr(self, 'floating_widget') and self.floating_widget and self.floating_widget.winfo_exists():
            self.floating_widget.update_timer(state, sec_left if is_running else 0, is_running)

        self.after(500, self._update_timer_loop)

    # ===== 2. Вкладка Библиотека правил =====

    def _build_rules_tab(self):
        top_bar = tk.Frame(self.tab_rules, bg=self.theme["bg_main"])
        top_bar.pack(fill="x", padx=8, pady=(10, 4))

        lbl_title = tk.Label(
            top_bar, text="Библиотека правил и приложений:",
            font=("Segoe UI", 12, "bold"),
            bg=self.theme["bg_main"], fg=self.theme["fg_text"]
        )
        lbl_title.pack(side="left")

        btn_add = tk.Button(
            top_bar, text="➕ Добавить правило", font=("Segoe UI", 9, "bold"),
            bg=self.theme["accent"], fg=self.theme["accent_fg"],
            relief="flat", cursor="hand2",
            command=self._open_add_rule_dialog
        )
        btn_add.pack(side="right", ipadx=10, ipady=3)

        info_frame = tk.Frame(
            self.tab_rules, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        info_frame.pack(fill="x", padx=8, pady=(4, 10))

        lbl_info = tk.Label(
            info_frame,
            text="💡 Здесь настраивается каталог доступных правил. Блокировки срабатывают только во время активной сессии таймера на Дашборде.",
            font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_muted"],
            anchor="w", justify="left", wraplength=580
        )
        lbl_info.pack(fill="x", anchor="w", padx=12, pady=8)

        info_frame.bind(
            "<Configure>",
            lambda e: lbl_info.config(wraplength=max(200, e.width - 28)) if lbl_info.winfo_exists() else None
        )

        list_container = tk.Frame(self.tab_rules, bg=self.theme["bg_main"])
        list_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.canvas_rules = tk.Canvas(list_container, bg=self.theme["bg_main"], borderwidth=0, highlightthickness=0)
        self.scrollbar_rules = AutoScrollbar(list_container, orient="vertical", command=self.canvas_rules.yview)
        self.rules_scrollable_frame = tk.Frame(self.canvas_rules, bg=self.theme["bg_main"])

        self.rules_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas_rules.configure(scrollregion=self.canvas_rules.bbox("all"))
        )

        self.canvas_rules_window = self.canvas_rules.create_window((0, 0), window=self.rules_scrollable_frame, anchor="nw")

        def _on_rules_canvas_configure(event):
            self.canvas_rules.itemconfig(self.canvas_rules_window, width=event.width)

        self.canvas_rules.bind("<Configure>", _on_rules_canvas_configure)
        self.canvas_rules.configure(yscrollcommand=self.scrollbar_rules.set)

        self.canvas_rules.pack(side="left", fill="both", expand=True)
        _bind_mousewheel_to_canvas(self.canvas_rules)

        self._refresh_rules_list()

    def _refresh_rules_list(self):
        for widget in self.rules_scrollable_frame.winfo_children():
            widget.destroy()

        rules = self.cfg.get_rules()
        for r in rules:
            card = tk.Frame(
                self.rules_scrollable_frame, bg=self.theme["bg_card"],
                highlightbackground=self.theme["border"], highlightthickness=1
            )
            card.pack(fill="x", expand=True, pady=4, padx=2)

            btn_del = tk.Button(
                card, text="🗑️", font=("Segoe UI", 10),
                bg=self.theme["bg_card"], fg=self.theme["accent_red"],
                relief="flat", cursor="hand2", command=lambda r_id=r.id: self._on_delete_rule(r_id)
            )
            btn_del.pack(side="right", padx=(4, 12), pady=8)

            btn_edit = tk.Button(
                card, text="✏️", font=("Segoe UI", 10),
                bg=self.theme["bg_card"], fg=self.theme["fg_text"],
                relief="flat", cursor="hand2", command=lambda rule=r: self._open_edit_rule_dialog(rule)
            )
            btn_edit.pack(side="right", padx=4, pady=8)

            if r.action == "close_tab":
                icon = "🌐"
            elif r.action == "minimize_window":
                icon = "🗕"
            else:
                icon = "📦"
            lbl_name = tk.Label(
                card, text=f"{icon} {r.name}", font=("Segoe UI", 10, "bold"),
                bg=self.theme["bg_card"], fg=self.theme["fg_text"]
            )
            lbl_name.pack(side="left", padx=(14, 6), pady=10)

    def _open_add_rule_dialog(self):
        RuleDialog(self, theme=self.theme, rule=None, on_save=self._on_rule_saved)

    def _open_edit_rule_dialog(self, rule: RuleConfig):
        RuleDialog(self, theme=self.theme, rule=rule, on_save=self._on_rule_saved)

    def _on_rule_saved(self, rule: RuleConfig):
        self.cfg.add_or_update_rule(rule)
        self._refresh_rules_list()
        self._refresh_dashboard_checkboxes()
        if hasattr(self, '_refresh_presets_list'):
            self._refresh_presets_list()

    def _on_delete_rule(self, rule_id: str):
        if messagebox.askyesno("Подтверждение", "Удалить это правило блокировки?", parent=self):
            self.cfg.delete_rule(rule_id)
            self._refresh_rules_list()
            self._refresh_dashboard_checkboxes()
            if hasattr(self, '_refresh_presets_list'):
                self._refresh_presets_list()

    # ===== 3. Вкладка Пресеты =====

    def _build_presets_tab(self):
        top_bar = tk.Frame(self.tab_presets, bg=self.theme["bg_main"])
        top_bar.pack(fill="x", padx=8, pady=(10, 4))

        lbl_title = tk.Label(
            top_bar, text="Пресеты сценариев фокуса:",
            font=("Segoe UI", 12, "bold"),
            bg=self.theme["bg_main"], fg=self.theme["fg_text"]
        )
        lbl_title.pack(side="left")

        btn_add = tk.Button(
            top_bar, text="➕ Создать пресет", font=("Segoe UI", 9, "bold"),
            bg=self.theme["accent"], fg=self.theme["accent_fg"],
            relief="flat", cursor="hand2",
            command=self._open_add_preset_dialog
        )
        btn_add.pack(side="right", ipadx=10, ipady=3)

        info_frame = tk.Frame(
            self.tab_presets, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        info_frame.pack(fill="x", padx=8, pady=(4, 10))

        lbl_info = tk.Label(
            info_frame,
            text="💡 Пресеты позволяют в 1 клик на Дашборде настраивать интервалы работы/фокуса и набор блокируемых правил.",
            font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_muted"],
            anchor="w", justify="left", wraplength=580
        )
        lbl_info.pack(fill="x", anchor="w", padx=12, pady=8)

        info_frame.bind(
            "<Configure>",
            lambda e: lbl_info.config(wraplength=max(200, e.width - 28)) if lbl_info.winfo_exists() else None
        )

        list_container = tk.Frame(self.tab_presets, bg=self.theme["bg_main"])
        list_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.canvas_presets = tk.Canvas(list_container, bg=self.theme["bg_main"], borderwidth=0, highlightthickness=0)
        self.scrollbar_presets = AutoScrollbar(list_container, orient="vertical", command=self.canvas_presets.yview)
        self.presets_scrollable_frame = tk.Frame(self.canvas_presets, bg=self.theme["bg_main"])

        self.presets_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas_presets.configure(scrollregion=self.canvas_presets.bbox("all"))
        )

        self.canvas_presets_window = self.canvas_presets.create_window((0, 0), window=self.presets_scrollable_frame, anchor="nw")

        def _on_presets_canvas_configure(event):
            self.canvas_presets.itemconfig(self.canvas_presets_window, width=event.width)

        self.canvas_presets.bind("<Configure>", _on_presets_canvas_configure)
        self.canvas_presets.configure(yscrollcommand=self.scrollbar_presets.set)

        self.canvas_presets.pack(side="left", fill="both", expand=True)
        _bind_mousewheel_to_canvas(self.canvas_presets)

        self._refresh_presets_list()

    def _refresh_presets_list(self):
        for widget in self.presets_scrollable_frame.winfo_children():
            widget.destroy()

        presets = self.cfg.get_presets()
        all_rules_map = {r.id: r.name for r in self.cfg.get_rules()}

        for p in presets:
            card = tk.Frame(
                self.presets_scrollable_frame, bg=self.theme["bg_card"],
                highlightbackground=self.theme["border"], highlightthickness=1
            )
            card.pack(fill="x", expand=True, pady=4, padx=2)

            btn_del = tk.Button(
                card, text="🗑️", font=("Segoe UI", 10),
                bg=self.theme["bg_card"], fg=self.theme["accent_red"],
                relief="flat", cursor="hand2", command=lambda p_id=p.id: self._on_delete_preset(p_id)
            )
            btn_del.pack(side="right", padx=(4, 12), pady=10)

            btn_edit = tk.Button(
                card, text="✏️", font=("Segoe UI", 10),
                bg=self.theme["bg_card"], fg=self.theme["fg_text"],
                relief="flat", cursor="hand2", command=lambda pr=p: self._open_edit_preset_dialog(pr)
            )
            btn_edit.pack(side="right", padx=4, pady=10)

            btn_apply = tk.Button(
                card, text="▶ Применить", font=("Segoe UI", 9, "bold"),
                bg=self.theme["bg_card_hover"], fg=self.theme["accent"],
                relief="flat", cursor="hand2", command=lambda pr=p: self._on_apply_preset_from_tab(pr)
            )
            btn_apply.pack(side="right", padx=(4, 8), pady=10, ipadx=6, ipady=2)

            left_frame = tk.Frame(card, bg=self.theme["bg_card"])
            left_frame.pack(side="left", fill="both", expand=True, padx=(14, 6), pady=8)

            lbl_name = tk.Label(
                left_frame, text=p.name, font=("Segoe UI", 10, "bold"),
                bg=self.theme["bg_card"], fg=self.theme["fg_text"], anchor="w"
            )
            lbl_name.pack(fill="x", anchor="w")

            rule_names = [all_rules_map.get(r_id, r_id) for r_id in p.rule_ids]
            rule_str = ", ".join(rule_names) if rule_names else "нет правил"

            if p.allow_min > 0:
                time_str = f"⏳ {p.allow_min} мин работы ➔ {p.block_min} мин блока  •  Блокирует: {rule_str}"
            else:
                time_str = f"🔒 Блок на {p.block_min} мин  •  Блокирует: {rule_str}"

            lbl_sub = tk.Label(
                left_frame, text=time_str, font=("Segoe UI", 8),
                bg=self.theme["bg_card"], fg=self.theme["fg_muted"], anchor="w"
            )
            lbl_sub.pack(fill="x", anchor="w", pady=(2, 0))

    def _open_add_preset_dialog(self, initial_preset: Optional[PresetConfig] = None):
        PresetDialog(
            self, theme=self.theme, preset=initial_preset,
            available_rules=self.cfg.get_rules(), on_save=self._on_preset_saved
        )

    def _open_edit_preset_dialog(self, preset: PresetConfig):
        PresetDialog(
            self, theme=self.theme, preset=preset,
            available_rules=self.cfg.get_rules(), on_save=self._on_preset_saved
        )

    def _on_preset_saved(self, preset: PresetConfig):
        self.cfg.add_or_update_preset(preset)
        self._refresh_presets_list()
        self._build_preset_buttons()
        self._check_preset_match()
        self._update_summary_label()

    def _on_delete_preset(self, preset_id: str):
        if messagebox.askyesno("Подтверждение", "Удалить этот пресет фокуса?", parent=self):
            self.cfg.delete_preset(preset_id)
            self._refresh_presets_list()
            self._build_preset_buttons()
            self._check_preset_match()
            self._update_summary_label()

    def _on_apply_preset_from_tab(self, preset: PresetConfig):
        self._apply_preset_to_dashboard(preset)
        self._switch_tab(0)

    # ===== 4. Вкладка Настройки =====

    def _build_settings_tab(self):
        settings_container = tk.Frame(self.tab_settings, bg=self.theme["bg_main"])
        settings_container.pack(fill="both", expand=True)

        self.canvas_settings = tk.Canvas(settings_container, bg=self.theme["bg_main"], borderwidth=0, highlightthickness=0)
        self.scrollbar_settings = AutoScrollbar(settings_container, orient="vertical", command=self.canvas_settings.yview)
        self.settings_scrollable_frame = tk.Frame(self.canvas_settings, bg=self.theme["bg_main"])

        self.settings_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas_settings.configure(scrollregion=self.canvas_settings.bbox("all"))
        )

        self.canvas_settings_window = self.canvas_settings.create_window((0, 0), window=self.settings_scrollable_frame, anchor="nw")

        def _on_settings_canvas_configure(event):
            self.canvas_settings.itemconfig(self.canvas_settings_window, width=event.width)

        self.canvas_settings.bind("<Configure>", _on_settings_canvas_configure)
        self.canvas_settings.configure(yscrollcommand=self.scrollbar_settings.set)

        self.canvas_settings.pack(side="left", fill="both", expand=True)
        _bind_mousewheel_to_canvas(self.canvas_settings)

        pad_x = 8

        # 0. Карточка темы оформления (Ezzick Coffee Theme)
        box_theme = tk.Frame(
            self.settings_scrollable_frame, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        box_theme.pack(fill="x", padx=pad_x, pady=(8, 10))

        lbl_theme_head = tk.Label(
            box_theme, text="🎨 Тема оформления (Ezzick Coffee)",
            font=("Segoe UI", 11, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"]
        )
        lbl_theme_head.pack(anchor="w", padx=16, pady=(12, 6))

        self.var_theme = tk.StringVar(value=self.current_theme_key)
        frame_theme_radios = tk.Frame(box_theme, bg=self.theme["bg_card"])
        frame_theme_radios.pack(anchor="w", padx=16, pady=(0, 12))

        for key, t_data in THEMES.items():
            rb = tk.Radiobutton(
                frame_theme_radios,
                text=t_data["name"],
                value=key,
                variable=self.var_theme,
                font=("Segoe UI", 10),
                bg=self.theme["bg_card"],
                fg=self.theme["fg_text"],
                selectcolor=self.theme["select_color"],
                activebackground=self.theme["bg_card"],
                activeforeground=self.theme["fg_text"],
                command=self._on_theme_changed
            )
            rb.pack(anchor="w", pady=2)

        # 1. Карточка уведомлений на экране
        box_notif = tk.Frame(
            self.settings_scrollable_frame, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        box_notif.pack(fill="x", padx=pad_x, pady=(0, 10))

        lbl_head = tk.Label(
            box_notif, text="🖥️ Уведомления на экране (OSD)",
            font=("Segoe UI", 11, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"]
        )
        lbl_head.pack(anchor="w", padx=16, pady=(12, 6))

        self.var_osd = tk.BooleanVar(value=self.cfg.get_setting("osd_enabled", True))
        cb_osd = tk.Checkbutton(
            box_notif, text="Показывать всплывающий OSD-баннер на экране",
            variable=self.var_osd, font=("Segoe UI", 10),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"],
            selectcolor=self.theme["select_color"], activebackground=self.theme["bg_card"],
            activeforeground=self.theme["fg_text"],
            command=lambda: self.cfg.set_setting("osd_enabled", self.var_osd.get())
        )
        cb_osd.pack(anchor="w", padx=16, pady=4)

        self.var_sound = tk.BooleanVar(value=self.cfg.get_setting("sound_enabled", True))
        cb_snd = tk.Checkbutton(
            box_notif, text="Воспроизводить звуковой сигнал (Chime)",
            variable=self.var_sound, font=("Segoe UI", 10),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"],
            selectcolor=self.theme["select_color"], activebackground=self.theme["bg_card"],
            activeforeground=self.theme["fg_text"],
            command=lambda: self.cfg.set_setting("sound_enabled", self.var_sound.get())
        )
        cb_snd.pack(anchor="w", padx=16, pady=(0, 8))

        # Выбор монитора
        lbl_mon = tk.Label(
            box_notif, text="Монитор для отображения OSD-баннеров:",
            font=("Segoe UI", 9, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_muted"]
        )
        lbl_mon.pack(anchor="w", padx=16, pady=(4, 4))

        mon_options = [
            ("Авто (2-й экран если подключен, иначе основной)", "auto"),
            ("Основной монитор (Primary)", "primary"),
            ("Второй монитор (Secondary)", "secondary")
        ]

        current_mon = self.cfg.get_setting("target_monitor", "auto")
        self.var_target_mon = tk.StringVar(value=current_mon)

        frame_mon_radios = tk.Frame(box_notif, bg=self.theme["bg_card"])
        frame_mon_radios.pack(anchor="w", padx=16, pady=(0, 10))

        for text, val in mon_options:
            rb = tk.Radiobutton(
                frame_mon_radios, text=text, value=val, variable=self.var_target_mon,
                font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_text"],
                selectcolor=self.theme["select_color"],
                activebackground=self.theme["bg_card"], activeforeground=self.theme["fg_text"],
                command=lambda: self.cfg.set_setting("target_monitor", self.var_target_mon.get())
            )
            rb.pack(anchor="w", pady=1)

        btn_test = tk.Button(
            box_notif, text="🔔 Проверить появление OSD на экране прямо сейчас", font=("Segoe UI", 9, "bold"),
            bg=self.theme["bg_input"], fg=self.theme["fg_text"], relief="flat", cursor="hand2",
            command=self._test_osd_banner
        )
        btn_test.pack(anchor="w", padx=16, pady=(4, 16), ipadx=10, ipady=4)

        # 2. Карточка быстрого контроля времени и микро-виджета
        box_peek = tk.Frame(
            self.settings_scrollable_frame, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        box_peek.pack(fill="x", padx=pad_x, pady=(0, 10))

        lbl_peek_head = tk.Label(
            box_peek, text="⚡ Быстрый контроль времени и виджеты",
            font=("Segoe UI", 11, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"]
        )
        lbl_peek_head.pack(anchor="w", padx=16, pady=(12, 6))

        self.var_settings_floating_widget = tk.BooleanVar(value=self.cfg.get_show_floating_widget())
        cb_float_set = tk.Checkbutton(
            box_peek, text="Показывать плавающий микро-виджет поверх окон",
            variable=self.var_settings_floating_widget, font=("Segoe UI", 10),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"],
            selectcolor=self.theme["select_color"], activebackground=self.theme["bg_card"],
            activeforeground=self.theme["fg_text"],
            command=self._on_toggle_floating_widget_from_settings
        )
        cb_float_set.pack(anchor="w", padx=16, pady=4)

        lbl_float_desc = tk.Label(
            box_peek,
            text="Компактная плашка таймера на экране. Можно перетаскивать мышкой, двойной клик открывает AppBlocker.",
            font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_muted"],
            anchor="w", justify="left"
        )
        lbl_float_desc.pack(fill="x", anchor="w", padx=16, pady=(0, 6))

        btn_reset_widget = tk.Button(
            box_peek, text="🎯 Найти и вернуть микро-виджет на экран (в центр)",
            font=("Segoe UI", 9, "bold"),
            bg=self.theme["bg_input"], fg=self.theme["accent"], relief="flat", cursor="hand2",
            activebackground=self.theme["bg_card_hover"], activeforeground=self.theme["accent_hover"],
            command=self._reset_and_highlight_floating_widget
        )
        btn_reset_widget.pack(anchor="w", padx=16, pady=(0, 12), ipadx=10, ipady=4)

        self.var_hotkey = tk.BooleanVar(value=self.cfg.get_enable_peek_hotkey())
        cb_hk = tk.Checkbutton(
            box_peek, text="Включить горячие клавиши проверки времени (F9 / Ctrl + Shift + B / Ctrl + Alt + B)",
            variable=self.var_hotkey, font=("Segoe UI", 10),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"],
            selectcolor=self.theme["select_color"], activebackground=self.theme["bg_card"],
            activeforeground=self.theme["fg_text"],
            command=self._on_toggle_hotkey
        )
        cb_hk.pack(anchor="w", padx=16, pady=4)

        lbl_hk_desc = tk.Label(
            box_peek,
            text="При нажатии F9 или Ctrl+Shift+B из любой программы на 1.8 сек появится аккуратный OSD-баннер с оставшимся временем.",
            font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_muted"],
            anchor="w", justify="left"
        )
        lbl_hk_desc.pack(fill="x", anchor="w", padx=16, pady=(0, 10))

        btn_test_peek = tk.Button(
            box_peek, text="⚡ Посмотреть остаток времени прямо сейчас (тест баннера)", font=("Segoe UI", 9, "bold"),
            bg=self.theme["bg_input"], fg=self.theme["fg_text"], relief="flat", cursor="hand2",
            command=lambda: show_quick_peek(session_controller, target_monitor=self.cfg.get_setting("target_monitor", "auto"))
        )
        btn_test_peek.pack(anchor="w", padx=16, pady=(0, 16), ipadx=10, ipady=4)

        # 3. Карточка автозапуска
        box_auto = tk.Frame(
            self.settings_scrollable_frame, bg=self.theme["bg_card"],
            highlightbackground=self.theme["border"], highlightthickness=1
        )
        box_auto.pack(fill="x", padx=pad_x, pady=(0, 14))

        lbl_auto_head = tk.Label(
            box_auto, text="🚀 Системный автозапуск",
            font=("Segoe UI", 11, "bold"), bg=self.theme["bg_card"], fg=self.theme["fg_text"]
        )
        lbl_auto_head.pack(anchor="w", padx=16, pady=(12, 6))

        self.var_autostart = tk.BooleanVar(value=is_autostart_enabled())
        cb_auto = tk.Checkbutton(
            box_auto, text="Запускать AppBlocker при старте Windows",
            variable=self.var_autostart, font=("Segoe UI", 10),
            bg=self.theme["bg_card"], fg=self.theme["fg_text"],
            selectcolor=self.theme["select_color"], activebackground=self.theme["bg_card"],
            activeforeground=self.theme["fg_text"],
            command=self._on_toggle_autostart
        )
        cb_auto.pack(anchor="w", padx=16, pady=4)

        lbl_auto_desc = tk.Label(
            box_auto,
            text="При включении программа будет запускаться в фоновом режиме в трее при входе в Windows.",
            font=("Segoe UI", 9), bg=self.theme["bg_card"], fg=self.theme["fg_muted"],
            anchor="w", justify="left"
        )
        lbl_auto_desc.pack(fill="x", anchor="w", padx=16, pady=(0, 14))

    def _on_theme_changed(self):
        new_theme_key = self.var_theme.get()
        if new_theme_key in THEMES and new_theme_key != self.current_theme_key:
            self.current_theme_key = new_theme_key
            self.cfg.set_theme(new_theme_key)
            self.theme = THEMES[new_theme_key]
            set_osd_theme(new_theme_key)
            if hasattr(self, 'floating_widget') and self.floating_widget and self.floating_widget.winfo_exists():
                self.floating_widget.apply_theme(self.theme)
            self._rebuild_all_ui()

    def _reset_and_highlight_floating_widget(self):
        """Возвращает микро-виджет в центр экрана на передний план и подсвечивает его."""
        self.var_settings_floating_widget.set(True)
        if hasattr(self, 'var_floating_widget'):
            self.var_floating_widget.set(True)
        self.cfg.set_show_floating_widget(True)
        self._init_floating_widget()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        target_x = max(20, (screen_w - 140) // 2)
        target_y = 80

        self.floating_widget.geometry(f"140x34+{target_x}+{target_y}")
        self.cfg.set_widget_position(target_x, target_y)
        self.floating_widget.show_widget()
        self.floating_widget.highlight_pulse()
        if hasattr(self, '_on_widget_visibility_changed'):
            self._on_widget_visibility_changed()
        try:
            from blocker_utils import play_notification_sound
            play_notification_sound("pop")
        except Exception:
            pass

    def _on_toggle_floating_widget_from_settings(self):
        show = self.var_settings_floating_widget.get()
        self.cfg.set_show_floating_widget(show)
        if show:
            self._init_floating_widget()
            self.floating_widget.show_widget()
        else:
            if self.floating_widget and self.floating_widget.winfo_exists():
                self.floating_widget.hide_widget()
        if hasattr(self, 'var_floating_widget'):
            self.var_floating_widget.set(show)

    def _on_toggle_hotkey(self):
        enabled = self.var_hotkey.get()
        self.cfg.set_enable_peek_hotkey(enabled)
        if enabled:
            if not self.hotkey_listener or not self.hotkey_listener._running:
                self.hotkey_listener = GlobalHotkeyListener(callback=lambda: self.after(0, show_quick_peek))
                self.hotkey_listener.start()
        else:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
                self.hotkey_listener = None

    def _on_toggle_autostart(self):
        val = self.var_autostart.get()
        success = set_autostart(val)
        if not success:
            messagebox.showerror("Ошибка", "Не удалось изменить автозагрузку в реестре.", parent=self)
            self.var_autostart.set(is_autostart_enabled())
        else:
            self.cfg.set_setting("autostart_enabled", val)

    def _test_osd_banner(self):
        target_mon = self.cfg.get_setting("target_monitor", "auto")
        show_osd_notification(
            title="AppBlocker (Тест)",
            message=f"🔔 Проверка уведомления на экране [{target_mon}]!",
            duration_sec=6.0,
            play_sound=self.var_sound.get(),
            target_monitor=target_mon
        )


if __name__ == '__main__':
    ensure_single_instance()
    app = AppBlockerGUI()
    app.mainloop()
