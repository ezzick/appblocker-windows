"""
TelegramBlock_after.pyw - Запуск сессии для Telegram (N мин работы -> M мин блокировки).
Совместимость с AutoHotKey меню и старыми ярлыками.
"""
import os
import sys
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SCRIPT_DIR, "src") if os.path.exists(os.path.join(SCRIPT_DIR, "src")) else (
    os.path.join(os.path.dirname(SCRIPT_DIR), "src") if os.path.exists(os.path.join(os.path.dirname(SCRIPT_DIR), "src")) else SCRIPT_DIR
)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from blocker_utils import AppRule, run_pomodoro_block_session, setup_logging

logger = setup_logging("TelegramBlock_after")

TELEGRAM_RULE = AppRule(
    name="Telegram",
    process_names=["Telegram.exe"],
    class_pattern="Telegram",
    action="close_window"
)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Блокировщик Telegram с гибкими опциями")
    parser.add_argument('pos_allow_min', nargs='?', type=int, default=None)
    parser.add_argument('pos_block_min', nargs='?', type=int, default=None)
    parser.add_argument('--allow_min', type=int, default=5)
    parser.add_argument('--block_min', type=int, default=5)
    parser.add_argument('--do_alert', action='store_true', default=False)
    args = parser.parse_args()

    allow_m = args.pos_allow_min if args.pos_allow_min is not None else args.allow_min
    block_m = args.pos_block_min if args.pos_block_min is not None else args.block_min

    try:
        run_pomodoro_block_session(
            rule=TELEGRAM_RULE,
            allow_min=int(allow_m),
            block_min=int(block_m),
            do_alert=bool(args.do_alert)
        )
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as ex:
        logger.critical(f"Error: {ex}", exc_info=True)
