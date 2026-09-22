"""
AppBlocker.pyw - Главная точка запуска графического интерфейса и CLI-сессий AppBlocker.
Запускается через pythonw.exe без окна консоли и без диалогов безопасности.
Поддерживает быстрый запуск пресетов и параметров сессии из командной строки и AutoHotkey.
"""

import os
import sys
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from app_gui import ensure_single_instance, AppBlockerGUI


def main():
    parser = argparse.ArgumentParser(description="AppBlocker - Управление фокусом и блокировка приложений")
    parser.add_argument('--preset', type=str, default=None, help="ID пресета (например: chats_work_25_5, quick_check, deep_focus_50, hard_block_3h, no_ai_50_10)")
    parser.add_argument('--allow_min', type=int, default=None, help="Минут до блокировки (рабочая фаза)")
    parser.add_argument('--block_min', type=int, default=None, help="Минут блокировки")
    parser.add_argument('pos_block_min', nargs='?', type=int, default=None, help="Позиционный аргумент: минут блокировки")
    parser.add_argument('--rules', type=str, default=None, help="ID правил через запятую")
    parser.add_argument('--do_alert', action='store_true', default=False, help="Предупреждение перед блокировкой")
    parser.add_argument('--minimized', action='store_true', default=False, help="Запуск сразу свернутым в трей")
    parser.add_argument('--gui', action='store_true', default=False, help="Принудительно показать окно")

    args, unknown = parser.parse_known_args()

    block_m = args.pos_block_min if args.pos_block_min is not None else args.block_min
    allow_m = args.allow_min
    preset_id = args.preset

    has_cli_session = (preset_id is not None) or (block_m is not None) or (allow_m is not None)

    ensure_single_instance(cli_session_args=args if has_cli_session else None)

    app = AppBlockerGUI(
        start_preset_id=preset_id,
        allow_min=allow_m,
        block_min=block_m,
        rule_ids=[r.strip() for r in args.rules.split(",")] if args.rules else None,
        start_minimized=(has_cli_session and not args.gui) or args.minimized
    )
    app.mainloop()


if __name__ == '__main__':
    main()
