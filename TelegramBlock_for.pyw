"""
TelegramBlock_for.pyw - Немедленная блокировка Telegram на N минут.
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

from blocker_utils import AppRule, run_blocking_loop, setup_logging

logger = setup_logging("TelegramBlock_for")

TELEGRAM_RULE = AppRule(
    name="Telegram",
    process_names=["Telegram.exe"],
    class_pattern="Telegram",
    action="close_window"
)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Блокировка Telegram на N минут")
    parser.add_argument('BlockMin', nargs='?', default='5')
    args = parser.parse_args()

    try:
        block_m = int(args.BlockMin)
        run_blocking_loop(rule=TELEGRAM_RULE, duration_sec=block_m * 60, poll_interval_sec=1.0)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as ex:
        logger.critical(f"Error: {ex}", exc_info=True)
