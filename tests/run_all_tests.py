"""
run_all_tests.py - Единый запуск всех автоматических unit-тестов AppBlocker.
"""

import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
SRC_DIR = os.path.join(PARENT_DIR, "src")

for p in (SRC_DIR, PARENT_DIR, CURRENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


import logging

def run_tests():
    print("=" * 65)
    print(" 🚀 Запуск полного набора unit-тестов AppBlocker...")
    print("=" * 65)

    # Направляем логи тестируемых модулей в отдельный файл отчета
    log_file = os.path.join(CURRENT_DIR, "test_run.log")
    logging.basicConfig(
        filename=log_file,
        filemode="w",
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    )
    # Отключаем вывод в консоль для корневого логгера и логгеров приложения
    app_logger = logging.getLogger("AppBlocker")
    app_logger.setLevel(logging.DEBUG)

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=CURRENT_DIR, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 65)
    if result.wasSuccessful():
        print(f" ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО! Запущено тестов: {result.testsRun}, Ошибок: 0")
        print("=" * 65)
        return 0
    else:
        print(f" ❌ ОБНАРУЖЕНЫ ОШИБКИ: Провалов={len(result.failures)}, Ошибок={len(result.errors)}")
        print("=" * 65)
        return 1


if __name__ == '__main__':
    exit_code = run_tests()
    sys.exit(exit_code)
