"""
AppBlocker.pyw - Главная точка запуска графического интерфейса AppBlocker.
Запускается через pythonw.exe без окна консоли и без диалогов безопасности.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from app_gui import ensure_single_instance, AppBlockerGUI

if __name__ == '__main__':
    ensure_single_instance()
    app = AppBlockerGUI()
    app.mainloop()