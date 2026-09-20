"""
build_exe.py - Автоматический скрипт сборки AppBlocker в автономный .exe через PyInstaller.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
ENTRY_POINT = os.path.join(SRC_DIR, "AppBlocker.pyw")
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "app_icon.ico")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
OUTPUT_EXE_NAME = "AppBlocker_v2.1"


def build():
    print("=" * 65)
    print(" 📦 Сборка AppBlocker в автономный executable (.exe)...")
    print("=" * 65)

    if not os.path.exists(ENTRY_POINT):
        print(f"❌ Ошибка: Не найден входной файл: {ENTRY_POINT}")
        return 1

    if not os.path.exists(ICON_PATH):
        print(f"⚠️ Предупреждение: Иконка не найдена по пути: {ICON_PATH}")

    try:
        import PyInstaller.__main__
    except ImportError:
        print("❌ Ошибка: PyInstaller не установлен в текущем Python-окружении!")
        print("Установите его командой: pip install pyinstaller")
        return 1

    # Аргументы сборки PyInstaller
    args = [
        ENTRY_POINT,
        f"--name={OUTPUT_EXE_NAME}",
        "--onefile",
        "--noconsole",
        f"--icon={ICON_PATH}",
        f"--add-data={ASSETS_DIR};assets",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        f"--specpath={BUILD_DIR}",
        f"--paths={SRC_DIR}",
        "--clean",
        "-y"
    ]

    print("Запуск PyInstaller с параметрами:")
    for arg in args:
        print(f"  {arg}")
    print("-" * 65)

    try:
        PyInstaller.__main__.run(args)
    except Exception as ex:
        print(f"❌ Ошибка во время сборки PyInstaller: {ex}")
        return 1

    exe_path = os.path.join(DIST_DIR, f"{OUTPUT_EXE_NAME}.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print("=" * 65)
        print(" ✅ СБОРКА УСПЕШНО ЗАВЕРШЕНА!")
        print(f" 📁 Исполняемый файл: {exe_path}")
        print(f" ⚖️  Размер: {size_mb:.2f} МБ")
        print("=" * 65)
        return 0
    else:
        print("❌ Ошибка: Итоговый .exe файл не обнаружен в dist/")
        return 1


if __name__ == '__main__':
    code = build()
    sys.exit(code)
