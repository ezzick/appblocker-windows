"""
run_tests.py - Централизованный диспетчер запуска тестов проекта AppBlocker.

Функционал:
- Автоматический сбор и запуск всех модульных и интеграционных тестов.
- Перенаправление подробного отчета в файл logs/test_report.txt.
- Формирование отчета об ошибках logs/test_failed.txt при сбоях.
- Информативный вывод статусов и времени выполнения в консоль.
- Поддержка параметров фильтрации (-k, --only, -v).
"""

import os
import sys
import time
import io
import argparse
import traceback
import logging
from typing import List, Dict, Callable, Any

# Принудительная установка UTF-8 для консоли Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Импорты тестовых модулей
from test_app_rules import run_tests as test_app_rules_fn
from test_config import run_tests as test_config_fn
from test_config_manager import run_tests as test_config_mgr_fn
from test_monitors import run_tests as test_monitors_fn
from test_notification import run_tests as test_notification_fn
from test_osd import run_tests as test_osd_fn
from test_session_controller import run_tests as test_session_fn


TEST_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": "app_rules",
        "name": "📐 Правила приложений и фильтры (AppRules)",
        "func": test_app_rules_fn,
        "tags": ["rules", "filter", "core"]
    },
    {
        "id": "config",
        "name": "⚙️  Модели конфигурации и пресеты (Config)",
        "func": test_config_fn,
        "tags": ["config", "models", "core"]
    },
    {
        "id": "config_manager",
        "name": "💾 Менеджер настроек (ConfigManager)",
        "func": test_config_mgr_fn,
        "tags": ["config", "manager", "storage"]
    },
    {
        "id": "monitors",
        "name": "🔍 Мониторинг процессов и окон Win32",
        "func": test_monitors_fn,
        "tags": ["monitors", "win32", "system"]
    },
    {
        "id": "notification",
        "name": "💬 Окна уведомлений и звуки (Notification)",
        "func": test_notification_fn,
        "tags": ["notification", "sound", "ui"]
    },
    {
        "id": "osd",
        "name": "⏱️  Оверлей OSD и мониторы",
        "func": test_osd_fn,
        "tags": ["osd", "overlay", "gui", "ui"]
    },
    {
        "id": "session_controller",
        "name": "🔄 Контроллер сессий и персистентность",
        "func": test_session_fn,
        "tags": ["session", "state", "controller", "core"]
    }
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Запуск тестов AppBlocker")
    parser.add_argument("-k", "--keyword", type=str, help="Фильтрация тестов по ключевому слову")
    parser.add_argument("-o", "--only", type=str, help="Запуск только указанных модулей через запятую")
    parser.add_argument("-v", "--verbose", action="store_true", help="Вывод подробного журнала каждого теста в консоль")
    args = parser.parse_args()

    os.makedirs(LOGS_DIR, exist_ok=True)
    report_file = os.path.join(LOGS_DIR, "test_report.txt")
    failed_file = os.path.join(LOGS_DIR, "test_failed.txt")

    # Фильтрация тестов
    selected_tests = list(TEST_REGISTRY)
    if args.only:
        targets = [t.strip().lower() for t in args.only.split(",") if t.strip()]
        selected_tests = [t for t in selected_tests if t["id"] in targets or any(tag in targets for tag in t["tags"])]

    if args.keyword:
        kws = [k.strip().lower() for k in args.keyword.split(",") if k.strip()]
        selected_tests = [
            t for t in selected_tests
            if any(
                kw in t["id"].lower() or kw in t["name"].lower() or any(kw in tag.lower() for tag in t["tags"])
                for kw in kws
            )
        ]

    if not selected_tests:
        print(f"❌ Не найдено тестов по критерию фильтра (only='{args.only}', -k='{args.keyword}')")
        return 1

    total_start_time = time.time()
    print("=" * 70)
    print("🧪 RUN_TESTS: Запуск тестового набора AppBlocker")
    print(f"🕒 Время старта: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Файл отчета: logs/test_report.txt")
    print(f"🔢 Отобрано модулей тестов: {len(selected_tests)} из {len(TEST_REGISTRY)}")
    print("=" * 70)

    all_logs_buffer: List[str] = [
        "=" * 70,
        f"📋 СВОДНЫЙ ОТЧЕТ ТЕСТИРОВАНИЯ: AppBlocker",
        f"⏰ Время запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70
    ]

    failed_list: List[Dict[str, Any]] = []
    passed_count = 0

    for idx, test_info in enumerate(selected_tests, start=1):
        test_id = test_info["id"]
        test_name = test_info["name"]
        test_fn = test_info["func"]

        # Перехват стандартного потока вывода и логгера
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured_stdout
        sys.stderr = captured_stderr

        ab_logger = logging.getLogger("AppBlocker")
        old_handlers = list(ab_logger.handlers)
        temp_handler = logging.StreamHandler(captured_stdout)
        temp_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        ab_logger.handlers = [h for h in old_handlers if not isinstance(h, logging.StreamHandler)] + [temp_handler]

        test_start = time.time()
        success = False
        err_msg = ""
        tb_str = ""

        try:
            res = test_fn()
            success = (res is not False)
        except Exception as ex:
            success = False
            err_msg = str(ex)
            tb_str = traceback.format_exc()
        finally:
            ab_logger.handlers = old_handlers
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            elapsed = time.time() - test_start

        log_output = (captured_stdout.getvalue() + "\n" + captured_stderr.getvalue()).strip()
        all_logs_buffer.append(f"\n--- [{idx}/{len(selected_tests)}] {test_name} ({test_id}) [{elapsed:.2f}s] ---")
        if log_output:
            all_logs_buffer.append(log_output)

        dots = "." * max(2, 44 - len(test_name))
        if success:
            passed_count += 1
            print(f"[{idx}/{len(selected_tests)}] {test_name} {dots} ✅ OK ({elapsed:.2f}s)")
        else:
            print(f"[{idx}/{len(selected_tests)}] {test_name} {dots} ❌ FAIL ({elapsed:.2f}s)")
            if err_msg:
                print(f"       Причина: {err_msg}")
            all_logs_buffer.append(f"❌ ОШИБКА: {err_msg}\n{tb_str}")
            failed_list.append({
                "id": test_id,
                "name": test_name,
                "error": err_msg or "Test failed",
                "traceback": tb_str or log_output
            })

        if args.verbose and log_output:
            print("-" * 50)
            print(log_output)
            print("-" * 50)

    total_elapsed = time.time() - total_start_time

    # Запись полного отчета в logs/test_report.txt
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("\n".join(all_logs_buffer) + "\n")
    except Exception as ex:
        print(f"⚠️ Не удалось сохранить {report_file}: {ex}")

    # Запись отчета об ошибках в logs/test_failed.txt
    if failed_list:
        try:
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write(f"❌ СБОИ ТЕСТИРОВАНИЯ ({len(failed_list)} ошибок) - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 70 + "\n")
                for item in failed_list:
                    f.write(f"\nМодуль: {item['name']} ({item['id']})\n")
                    f.write(f"Ошибка: {item['error']}\n")
                    f.write(f"Стектрейс / Журнал:\n{item['traceback']}\n")
                    f.write("-" * 70 + "\n")
        except Exception:
            pass
    else:
        try:
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write("✅ Все тесты пройдены успешно (0 ошибок).\n")
        except Exception:
            pass

    print("-" * 70)
    if passed_count == len(selected_tests):
        print(f"🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО ({passed_count}/{len(selected_tests)}) за {total_elapsed:.2f}s!")
        print(f"📄 Полный детальный журнал сохранен в: logs/test_report.txt")
        print("=" * 70)
        return 0
    else:
        print(f"❌ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО С ОШИБКАМИ: Успешно: {passed_count}, Сбоев: {len(failed_list)}")
        print(f"📄 Подробности упавших тестов: logs/test_failed.txt")
        print(f"📄 Полный журнал: logs/test_report.txt")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
