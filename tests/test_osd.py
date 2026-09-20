import time
import blocker_utils

if __name__ == '__main__':
    print("Testing show_osd_notification...")
    blocker_utils.show_osd_notification("Тест Уведомления", "Проверка отображения уведомления на экране!", 5.0)
    time.sleep(6)
    print("Done test.")