import time
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from blocker_utils import show_osd_notification

if __name__ == '__main__':
    print("Запуск тестового OSD-уведомления...")
    show_osd_notification(
        title="Telegram Blocker (Тест)",
        message="⏳ До блокировки Telegram осталась 1 минута!",
        duration_sec=6.0,
        play_sound=True
    )

    time.sleep(7)
    print("Тест завершен.")