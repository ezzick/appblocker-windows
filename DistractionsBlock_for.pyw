"""
DistractionsBlock_for.pyw - Режим глубокого фокуса без соцсетей и видео на N минут.
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

from blocker_utils import AppRule, run_blocking_loop, setup_logging, show_osd_notification

logger = setup_logging("DistractionsBlock")

DISTRACTIONS_RULE = AppRule(
    name="Соцсети и видео (YouTube, VK и др.)",
    process_names=["chrome.exe", "firefox.exe", "msedge.exe", "opera.exe", "brave.exe", "yandex.exe"],
    title_blacklist=["YouTube", "ВКонтакте", "VK", "TikTok", "Instagram", "Reddit", "Twitter", "X.com", "Twitch", "Dzen"],
    action="close_tab"
)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Режим фокуса без отвлечений")
    parser.add_argument('BlockMin', nargs='?', default='50')
    args = parser.parse_args()

    try:
        block_m = int(args.BlockMin)
        show_osd_notification(
            title="Режим фокуса включен",
            message=f"🎯 Фокус на {block_m} мин. Соцсети и видео блокируются!",
            duration_sec=5.0,
            play_sound=True
        )
        run_blocking_loop(rule=DISTRACTIONS_RULE, duration_sec=block_m * 60, poll_interval_sec=1.0)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as ex:
        logger.critical(f"Error: {ex}", exc_info=True)
