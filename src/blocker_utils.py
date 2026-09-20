"""
blocker_utils.py - Универсальный Win32 API движок AppBlocker.

Функционал:
- Кросс-версионная поддержка Python 3.10-3.14 (аккуратный фолбэк для HCURSOR/HMONITOR)
- Чистый ctypes без сторонних pip-зависимостей (psutil, pywin32 и др. НЕ требуются)
- Работает нативно в 64-битной Windows (все типы строго 64-bit совместимы)
- Поиск процессов и окон без перехвата фокуса
- Закрытие процессов (WM_CLOSE) и умное закрытие отдельных вкладок браузера (Ctrl+W)
- Нативные OSD-баннеры поверх всех окон без кражи фокуса (WS_EX_NOACTIVATE, SW_SHOWNOACTIVATE)
- Поддержка тем оформления OSD (Ezzick Coffee Dark / Light)
- Автовыбор целевого монитора (Auto/Primary/Secondary)
- Фоновый контроллер сессий фокуса (SessionController)
- Сохранение и восстановление активных сессий (Persistent Sessions)
"""

import sys
import os
import time
import re
import json
import ctypes
from ctypes import wintypes
import logging
from logging.handlers import RotatingFileHandler
import threading
import winsound
import shutil
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def get_resource_path(relative_path: str) -> str:
    """
    Возвращает абсолютный путь к ресурсу (иконкам, ассетам),
    поддерживая как обычный запуск из исходников, так и упакованный бинарник .exe (PyInstaller _MEIPASS / Nuitka).
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.normpath(os.path.join(sys._MEIPASS, relative_path))

    # Сначала проверяем путь относительно SCRIPT_DIR (папка src)
    path_in_src = os.path.normpath(os.path.join(SCRIPT_DIR, relative_path))
    if os.path.exists(path_in_src):
        return path_in_src

    # Затем проверяем относительно корня проекта
    path_in_root = os.path.normpath(os.path.join(PROJECT_ROOT, relative_path))
    if os.path.exists(path_in_root):
        return path_in_root

    return path_in_src

# ===== Настройка путей в %APPDATA% и ротируемого логирования =====

def get_app_data_dir() -> str:
    """Возвращает путь к рабочей папке приложения в %APPDATA%\\AppBlocker."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = os.path.join(appdata, "AppBlocker")
    else:
        base = os.path.join(SCRIPT_DIR, "data")
    os.makedirs(base, exist_ok=True)
    return base

def get_log_dir() -> str:
    """Возвращает путь к папке логов %APPDATA%\\AppBlocker\\logs."""
    log_dir = os.path.join(get_app_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

SESSION_STATE_FILE = os.path.join(get_app_data_dir(), "session_state.json")

def setup_logging(logger_name: str = "AppBlocker") -> logging.Logger:
    """Настраивает ротируемый файловый логгер в %APPDATA% и вывод в консоль."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 1. Файловый логгер с ротацией в %APPDATA%\AppBlocker\logs\appblocker.log
        try:
            log_dir = get_log_dir()
            log_file = os.path.join(log_dir, "appblocker.log")
            fh = RotatingFileHandler(
                log_file,
                maxBytes=2 * 1024 * 1024,  # 2 МБ на файл
                backupCount=5,              # хранить 5 архивов
                encoding="utf-8"
            )
            fh.setFormatter(formatter)
            fh.setLevel(logging.INFO)
            logger.addHandler(fh)
        except Exception:
            pass

        # 2. Консольный вывод (для интерактивной отладки и CLI)
        if sys.stdout is not None:
            try:
                ch = logging.StreamHandler(sys.stdout)
                ch.setFormatter(formatter)
                ch.setLevel(logging.INFO)
                logger.addHandler(ch)
            except Exception:
                pass

    return logger

logger = setup_logging()

# ===== Определение структур Win32 API и безопасных типов ctypes =====

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32

LRESULT = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
COLORREF = wintypes.DWORD

# Фолбэк для отсутствующих типов в Python 3.10
for handle_type in ['HCURSOR', 'HICON', 'HBRUSH', 'HFONT', 'HGDIOBJ', 'HMONITOR']:
    if not hasattr(wintypes, handle_type):
        setattr(wintypes, handle_type, wintypes.HANDLE)

WM_CLOSE = 0x0010
WM_PAINT = 0x000F
WM_TIMER = 0x0113
WM_DESTROY = 0x0002
WM_ERASEBKGND = 0x0014

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

SW_SHOWNOACTIVATE = 4
SM_CXSCREEN = 0
SM_CYSCREEN = 1
TRANSPARENT = 1
DT_LEFT = 0x0000
DT_WORDBREAK = 0x0010
DT_SINGLELINE = 0x0020

VK_CONTROL = 0x11
VK_W = 0x57
KEYEVENTF_KEYUP = 0x0002

LPARAM_64 = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
WPARAM_64 = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint
LRESULT_64 = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, LPARAM_64)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT_64, wintypes.HWND, wintypes.UINT, WPARAM_64, LPARAM_64)


class RECT(ctypes.Structure):
    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long)
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ('hdc', wintypes.HDC),
        ('fErase', wintypes.BOOL),
        ('rcPaint', RECT),
        ('fRestore', wintypes.BOOL),
        ('fIncUpdate', wintypes.BOOL),
        ('rgbReserved', ctypes.c_byte * 32)
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ('style', wintypes.UINT),
        ('lpfnWndProc', WNDPROC),
        ('cbClsExtra', ctypes.c_int),
        ('cbWndExtra', ctypes.c_int),
        ('hInstance', wintypes.HINSTANCE),
        ('hIcon', wintypes.HICON),
        ('hCursor', wintypes.HCURSOR),
        ('hbrBackground', wintypes.HBRUSH),
        ('lpszMenuName', wintypes.LPCWSTR),
        ('lpszClassName', wintypes.LPCWSTR)
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('rcMonitor', RECT),
        ('rcWork', RECT),
        ('dwFlags', wintypes.DWORD)
    ]

MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HMONITOR,
    wintypes.HDC,
    ctypes.POINTER(RECT),
    wintypes.LPARAM
)

# Настройка сигнатур функций user32
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM_64, LPARAM_64]
user32.PostMessageW.restype = wintypes.BOOL

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.keybd_event.argtypes = [ctypes.c_byte, ctypes.c_byte, wintypes.DWORD, ctypes.c_size_t]
user32.keybd_event.restype = None

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM_64, LPARAM_64]
user32.DefWindowProcW.restype = LRESULT_64

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL

user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.UpdateWindow.restype = wintypes.BOOL

user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL

user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
user32.SetTimer.restype = ctypes.c_size_t

user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.KillTimer.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.PeekMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.c_void_p]
user32.TranslateMessage.restype = wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
user32.DispatchMessageW.restype = LRESULT

user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None

user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = wintypes.HDC

user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.restype = wintypes.BOOL

user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.restype = wintypes.BOOL

user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
user32.FillRect.restype = ctypes.c_int

user32.FrameRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
user32.FrameRect.restype = ctypes.c_int

user32.DrawTextW.argtypes = [
    wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
    ctypes.POINTER(RECT), wintypes.UINT
]
user32.DrawTextW.restype = ctypes.c_int

user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadCursorW.restype = wintypes.HCURSOR

user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON

user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE

user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT

user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), MONITORENUMPROC, wintypes.LPARAM]
user32.EnumDisplayMonitors.restype = wintypes.BOOL

user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL

user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, WPARAM_64, LPARAM_64]
user32.PostThreadMessageW.restype = wintypes.BOOL

# Настройка сигнатур функций kernel32
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

# Настройка сигнатур функций gdi32
gdi32.CreateSolidBrush.argtypes = [COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH

gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL

gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ

gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int

gdi32.SetTextColor.argtypes = [wintypes.HDC, COLORREF]
gdi32.SetTextColor.restype = COLORREF

gdi32.CreateFontW.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.DWORD, wintypes.LPCWSTR
]
gdi32.CreateFontW.restype = wintypes.HFONT


def _rgb(r: int, g: int, b: int) -> int:
    return (b << 16) | (g << 8) | r


# ===== Управление сохранением состояния сессии =====

def save_session_state(state_data: Dict[str, Any]):
    try:
        with open(SESSION_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_data, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        logger.debug(f"Failed to save session state: {ex}")


def load_session_state() -> Optional[Dict[str, Any]]:
    # Авто-миграция старого файла состояния из папки скрипта при его наличии
    if not os.path.exists(SESSION_STATE_FILE):
        old_state_file = os.path.join(SCRIPT_DIR, "session_state.json")
        if os.path.exists(old_state_file):
            try:
                shutil.copy2(old_state_file, SESSION_STATE_FILE)
                logger.info(f"Мигрирован файл состояния сессии из {old_state_file} в {SESSION_STATE_FILE}")
            except Exception as ex:
                logger.debug(f"Не удалось мигрировать старое состояние сессии: {ex}")

    if not os.path.exists(SESSION_STATE_FILE):
        return None
    try:
        with open(SESSION_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        logger.debug(f"Failed to load session state: {ex}")
        return None


def clear_session_state():
    try:
        if os.path.exists(SESSION_STATE_FILE):
            os.remove(SESSION_STATE_FILE)
        old_state_file = os.path.join(SCRIPT_DIR, "session_state.json")
        if os.path.exists(old_state_file):
            os.remove(old_state_file)
    except Exception as ex:
        logger.debug(f"Failed to clear session state: {ex}")


# ===== Управление темой OSD =====

_osd_theme = "dark"

def set_osd_theme(theme_name: str):
    global _osd_theme
    _osd_theme = "light" if theme_name == "light" else "dark"

def get_osd_theme() -> str:
    return _osd_theme


def get_target_monitor_work_area(target_mode: str = "auto") -> RECT:
    """
    Возвращает рабочую область монитора в зависимости от режима:
    - 'auto': 2-й экран (если подключен), иначе основной
    - 'primary': основной монитор
    - 'secondary': 2-й экран (если подключен), иначе основной
    """
    monitors: List[Dict[str, Any]] = []

    def enum_mon_proc(hmon, hdc, lprc, lparam):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            is_primary = bool(mi.dwFlags & 1)
            monitors.append({
                "rcWork": mi.rcWork,
                "rcMonitor": mi.rcMonitor,
                "is_primary": is_primary
            })
        return True

    cb = MONITORENUMPROC(enum_mon_proc)
    user32.EnumDisplayMonitors(0, None, cb, 0)

    if not monitors:
        sw = user32.GetSystemMetrics(SM_CXSCREEN)
        sh = user32.GetSystemMetrics(SM_CYSCREEN)
        return RECT(0, 0, sw, sh)

    primary_mon = next((m for m in monitors if m["is_primary"]), monitors[0])
    secondary_mon = next((m for m in monitors if not m["is_primary"]), None)

    if target_mode == "primary":
        return primary_mon["rcWork"]
    elif target_mode == "secondary":
        return secondary_mon["rcWork"] if secondary_mon else primary_mon["rcWork"]
    else:  # "auto"
        return secondary_mon["rcWork"] if secondary_mon else primary_mon["rcWork"]


# Потокобезопасное хранилище данных активных OSD окон (защита от race condition)
_osd_windows_data: Dict[int, tuple[str, str]] = {}
_osd_data_lock = threading.Lock()
_osd_class_lock = threading.Lock()


def _global_osd_wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_PAINT:
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))

        rect = RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))

        if _osd_theme == "light":
            # Ezzick Coffee Light palette
            bg_brush = gdi32.CreateSolidBrush(_rgb(236, 224, 209))      # #ece0d1
            accent_brush = gdi32.CreateSolidBrush(_rgb(194, 133, 75))   # #c2854b
            frame_brush = gdi32.CreateSolidBrush(_rgb(188, 172, 155))   # #bcac9b
            title_rgb = _rgb(56, 34, 15)                                # #38220f
            msg_rgb = _rgb(107, 85, 66)                                 # #6b5542
        else:
            # Ezzick Coffee Dark palette
            bg_brush = gdi32.CreateSolidBrush(_rgb(22, 22, 22))         # #161616
            accent_brush = gdi32.CreateSolidBrush(_rgb(198, 177, 139))  # #c6b18b
            frame_brush = gdi32.CreateSolidBrush(_rgb(90, 90, 90))      # #5a5a5a
            title_rgb = _rgb(247, 249, 252)                             # #f7f9fc
            msg_rgb = _rgb(185, 185, 185)                               # #b9b9b9

        user32.FillRect(hdc, ctypes.byref(rect), bg_brush)
        gdi32.DeleteObject(bg_brush)

        accent_rect = RECT(rect.left, rect.top, rect.right, rect.top + 4)
        user32.FillRect(hdc, ctypes.byref(accent_rect), accent_brush)
        gdi32.DeleteObject(accent_brush)

        user32.FrameRect(hdc, ctypes.byref(rect), frame_brush)
        gdi32.DeleteObject(frame_brush)

        gdi32.SetBkMode(hdc, TRANSPARENT)

        with _osd_data_lock:
            osd_title, osd_message = _osd_windows_data.get(hwnd, ("AppBlocker", ""))

        # Заголовок
        hfont_title = gdi32.CreateFontW(
            22, 0, 0, 0, 700, 0, 0, 0,
            1, 0, 0, 5, 0, "Segoe UI"
        )
        old_font = gdi32.SelectObject(hdc, hfont_title)
        gdi32.SetTextColor(hdc, title_rgb)

        title_rect = RECT(rect.left + 20, rect.top + 14, rect.right - 20, rect.top + 40)
        user32.DrawTextW(hdc, osd_title, -1, ctypes.byref(title_rect), DT_LEFT | DT_SINGLELINE)

        # Текст сообщения
        hfont_msg = gdi32.CreateFontW(
            18, 0, 0, 0, 400, 0, 0, 0,
            1, 0, 0, 5, 0, "Segoe UI"
        )
        gdi32.SelectObject(hdc, hfont_msg)
        gdi32.SetTextColor(hdc, msg_rgb)

        msg_rect = RECT(rect.left + 20, rect.top + 44, rect.right - 20, rect.bottom - 10)
        user32.DrawTextW(hdc, osd_message, -1, ctypes.byref(msg_rect), DT_LEFT | DT_WORDBREAK)

        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(hfont_title)
        gdi32.DeleteObject(hfont_msg)

        user32.EndPaint(hwnd, ctypes.byref(ps))
        return 0

    elif msg == WM_TIMER:
        user32.KillTimer(hwnd, wparam)
        user32.DestroyWindow(hwnd)
        return 0

    elif msg == WM_DESTROY:
        with _osd_data_lock:
            _osd_windows_data.pop(hwnd, None)
        user32.PostQuitMessage(0)
        return 0

    elif msg == WM_ERASEBKGND:
        return 1

    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_GLOBAL_WNDPROC_REF = WNDPROC(_global_osd_wndproc)
_osd_class_atom = None


def _osd_thread_func(title: str, message: str, duration_sec: float, play_sound: bool, target_monitor: str = "auto"):
    global _osd_class_atom

    if play_sound:
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

    hinstance = kernel32.GetModuleHandleW(None)
    class_name = "AppBlockerOSDClassV9"

    with _osd_class_lock:
        if not _osd_class_atom:
            wc = WNDCLASSW()
            wc.style = 0x0002 | 0x0001
            wc.lpfnWndProc = _GLOBAL_WNDPROC_REF
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinstance
            wc.hIcon = 0
            wc.hCursor = user32.LoadCursorW(None, wintypes.LPCWSTR(32512))
            wc.hbrBackground = 0
            wc.lpszMenuName = None
            wc.lpszClassName = class_name
            _osd_class_atom = user32.RegisterClassW(ctypes.byref(wc))

    w = 520
    h = 86

    target_rect = get_target_monitor_work_area(target_monitor)
    mon_width = target_rect.right - target_rect.left
    mon_left = target_rect.left
    mon_top = target_rect.top

    x = mon_left + (mon_width - w) // 2
    y = mon_top + 30

    ex_style = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    style = WS_POPUP

    hwnd = user32.CreateWindowExW(
        ex_style,
        class_name,
        "AppBlockerNotification",
        style,
        x, y, w, h,
        0, 0, hinstance, None
    )

    if not hwnd:
        err = kernel32.GetLastError()
        logger.error(f"Failed to create OSD window. LastError = {err}")
        return

    with _osd_data_lock:
        _osd_windows_data[hwnd] = (title, message)

    user32.SetTimer(hwnd, 1, int(duration_sec * 1000), None)
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.UpdateWindow(hwnd)

    msg = ctypes.wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


def show_osd_notification(
    title: str,
    message: str,
    duration_sec: float = 7.0,
    play_sound: bool = True,
    target_monitor: str = "auto"
):
    t = threading.Thread(
        target=_osd_thread_func,
        args=(title, message, duration_sec, play_sound, target_monitor),
        daemon=True
    )
    t.start()


def show_quick_peek(controller=None, target_monitor: str = "auto"):
    """Показывает компактное OSD-уведомление с остатком времени на 2.5 сек (без звука)."""
    ctrl = controller or session_controller
    try:
        st = ctrl.get_status()
    except Exception:
        st = {
            "is_active": ctrl.is_running(),
            "state": getattr(ctrl, "state", SessionState.STOPPED),
            "remaining_sec": getattr(ctrl, "get_seconds_remaining", lambda: 0)()
        }
    state = st.get("state")
    is_active = st.get("is_active", False)
    rem = st.get("remaining_sec", 0)
    m, s = divmod(max(0, int(rem)), 60)

    if not is_active or state == SessionState.STOPPED:
        title = "☕ AppBlocker — Таймер"
        msg = "Сессия сейчас не активна\nЗапустите таймер или пресет на главном экране"
    elif state == SessionState.WORK_PHASE:
        title = "⏳ До блокировки"
        msg = f"До начала блокировки: {m:02d}:{s:02d}"
    elif state == SessionState.BLOCK_PHASE:
        title = "🔒 Блокировка"
        msg = f"До окончания блокировки: {m:02d}:{s:02d}"
    else:
        title = "☕ AppBlocker"
        msg = f"Осталось времени: {m:02d}:{s:02d}"

    show_osd_notification(
        title=title,
        message=msg,
        duration_sec=2.5,
        play_sound=False,
        target_monitor=target_monitor
    )


class GlobalHotkeyListener:
    """Глобальный перехватчик горячих клавиш (Win+Alt+T и Ctrl+Shift+B) для быстрого подгляда."""

    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._thread_id = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()

        # Принудительно создаем и инициализируем очередь сообщений Windows для потока
        msg = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)

        WM_HOTKEY = 0x0312
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_WIN = 0x0008
        MOD_NOREPEAT = 0x4000

        # Регистрируем комбинации (с фолбэком без MOD_NOREPEAT)
        registered_ids = []
        hotkeys_to_register = [
            (101, MOD_CONTROL | MOD_SHIFT, ord('B'), "Ctrl+Shift+B"),
            (102, MOD_CONTROL | MOD_ALT, ord('B'), "Ctrl+Alt+B"),
            (103, MOD_CONTROL | MOD_SHIFT, ord('T'), "Ctrl+Shift+T"),
            (104, MOD_WIN | MOD_ALT, ord('T'), "Win+Alt+T"),
            (105, 0, 0x78, "F9"),  # F9 (VK_F9 = 0x78)
        ]

        for hk_id, mods, vk, name in hotkeys_to_register:
            res = user32.RegisterHotKey(0, hk_id, mods | MOD_NOREPEAT, vk)
            if not res:
                res = user32.RegisterHotKey(0, hk_id, mods, vk)
            if res:
                registered_ids.append(hk_id)
                logger.info(f"Hotkey registered: {name} (id={hk_id})")
            else:
                logger.debug(f"Hotkey {name} skipped/busy (LastError={kernel32.GetLastError()})")

        while self._running:
            res = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if res <= 0:
                break
            if msg.message == WM_HOTKEY:
                try:
                    if self.callback:
                        self.callback()
                except Exception as ex:
                    logger.error(f"Ошибка вызова callback горячей клавиши: {ex}")
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        for hk_id in registered_ids:
            try:
                user32.UnregisterHotKey(0, hk_id)
            except Exception:
                pass

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT


# ===== Управление окнами и вкладками =====

def close_active_tab(hwnd: int):
    """Отправляет сочетание клавиш Ctrl+W для закрытия только текущей вкладки."""
    try:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.05)
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_W, 0, 0, 0)
        user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    except Exception as ex:
        logger.debug(f"Failed to send Ctrl+W to hwnd {hwnd}: {ex}")


def get_window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_QUERY_INFORMATION = 0x0400


def get_process_name(hwnd: int) -> str:
    """Возвращает имя исполняемого файла (.exe) процесса окна."""
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ""

        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h_proc:
            h_proc = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid.value)
        if not h_proc:
            return ""

        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
            return ""
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception as ex:
        logger.debug(f"get_process_name error for hwnd {hwnd}: {ex}")
        return ""


def get_running_windows_list() -> List[Dict[str, Any]]:
    """Возвращает список видимых пользовательских окон для Window Picker."""
    results: List[Dict[str, Any]] = []

    def enum_windows_proc(hwnd, lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            title = get_window_text(hwnd)
            if not title or not title.strip():
                return True
            proc_name = get_process_name(hwnd)
            if not proc_name:
                return True

            if proc_name.lower() in [
                "explorer.exe", "searchhost.exe", "shellexperiencehost.exe",
                "textinputhost.exe", "applicationframehost.exe", "systemsettings.exe"
            ]:
                return True

            cls = get_window_class(hwnd)
            results.append({
                "hwnd": hwnd,
                "title": title,
                "process_name": proc_name,
                "class_name": cls
            })
        except Exception as ex:
            logger.debug(f"enum_windows_proc error: {ex}")
        return True

    cb = WNDENUMPROC(enum_windows_proc)
    user32.EnumWindows(cb, 0)
    return results


# ===== Модель правила блокировки =====

@dataclass
class AppRule:
    name: str
    process_names: List[str] = field(default_factory=list)
    class_pattern: Optional[str] = None
    exact_classes: List[str] = field(default_factory=list)
    title_whitelist: List[str] = field(default_factory=list)
    title_blacklist: List[str] = field(default_factory=list)
    action: str = "close_window"  # "close_window", "minimize_window", "close_tab"

    def matches(self, hwnd: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return False

        title = get_window_text(hwnd)
        cls = get_window_class(hwnd)
        proc = get_process_name(hwnd)

        if self.process_names:
            proc_lower = proc.lower()
            if not any(p.lower() == proc_lower for p in self.process_names):
                return False

        if self.exact_classes and cls not in self.exact_classes:
            return False

        if self.class_pattern and not re.search(self.class_pattern, cls):
            return False

        if self.title_whitelist:
            for w in self.title_whitelist:
                if w.lower() in title.lower():
                    return False

        if self.title_blacklist:
            for b in self.title_blacklist:
                if b.lower() in title.lower():
                    return True
            return False

        return True


def close_matching_windows(rule: AppRule) -> int:
    """Находит и закрывает или сворачивает все окна/вкладки, попадающие под правило."""
    hwnds_to_handle: List[int] = []

    def enum_cb(hwnd, lparam):
        if rule.matches(hwnd):
            hwnds_to_handle.append(hwnd)
        return True

    cb = WNDENUMPROC(enum_cb)
    user32.EnumWindows(cb, 0)

    handled_count = 0
    for hwnd in hwnds_to_handle:
        try:
            title = get_window_text(hwnd)
            class_name = get_window_class(hwnd)
            if rule.action == "close_tab":
                logger.info(f"Closing tab: '{title}' (hwnd={hwnd}) via Ctrl+W")
                close_active_tab(hwnd)
                show_osd_notification(
                    title="Вкладка заблокирована",
                    message=f"🔒 Закрыта отвлекающая вкладка:\n{title[:45]}...",
                    duration_sec=3.5,
                    play_sound=True
                )
                handled_count += 1
            elif rule.action == "minimize_window":
                # Если окно уже свёрнуто, ничего не делаем, чтобы не спамить
                if not user32.IsIconic(hwnd):
                    logger.info(f"Minimizing window: '{title}' (class='{class_name}', hwnd={hwnd}) under rule '{rule.name}'")
                    SW_MINIMIZE = 6
                    user32.ShowWindow(hwnd, SW_MINIMIZE)
                    show_osd_notification(
                        title="Приложение свёрнуто",
                        message=f"🔒 {rule.name} свёрнуто во время блокировки:\n{title[:45]}...",
                        duration_sec=3.0,
                        play_sound=True
                    )
                    handled_count += 1
            else:
                logger.info(f"Closing window: '{title}' (class='{class_name}', hwnd={hwnd}) under rule '{rule.name}'")
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                handled_count += 1
        except Exception as ex:
            logger.debug(f"Failed to process hwnd {hwnd}: {ex}")
    return handled_count


def close_multiple_rules(rules: List[AppRule]) -> int:
    """Закрывает окна/вкладки по списку переданных правил."""
    total = 0
    for rule in rules:
        total += close_matching_windows(rule)
    return total


def run_blocking_loop(
    rule: AppRule,
    duration_sec: float,
    poll_interval_sec: float = 1.0,
    on_tick: Optional[Callable[[float], None]] = None
):
    end_time = time.time() + duration_sec
    logger.info(f"Block '{rule.name}' started until {time.ctime(end_time)} ({int(duration_sec // 60)} min / {int(duration_sec)}s)")

    while time.time() < end_time:
        close_matching_windows(rule)
        if on_tick:
            try:
                on_tick(max(0.0, end_time - time.time()))
            except Exception as ex:
                logger.debug(f"on_tick callback error: {ex}")
        time.sleep(poll_interval_sec)

    logger.info(f"Block '{rule.name}' finished.")


def run_pomodoro_block_session(
    rule: AppRule,
    allow_min: int,
    block_min: int = 5,
    do_alert: bool = True
):
    allow_endtime = time.time() + allow_min * 60
    logger.info(f"=== Session Start: {rule.name} ===")
    logger.info(f"{rule.name} allowed for {allow_min} min (until {time.ctime(allow_endtime)}), followed by {block_min} min block.")

    alert_shown = False
    s_left = 1

    while time.time() < allow_endtime:
        remaining = allow_endtime - time.time()

        if do_alert and not alert_shown and remaining <= 60.0:
            alert_shown = True
            logger.info(f"Alert: 1 minute remaining before {rule.name} is blocked!")
            show_osd_notification(
                title=f"{rule.name} Blocker",
                message=f"⏳ До блокировки {rule.name} осталась 1 минута!",
                duration_sec=10.0,
                play_sound=True
            )

        if remaining > 60.0:
            sleep_duration = min(60.0, remaining - 60.0)
            time.sleep(max(1.0, sleep_duration))
            logger.info(f"Work phase: {s_left} min elapsed, ~{int((allow_endtime - time.time()) // 60) + 1} min remaining.")
            s_left += 1
        else:
            time.sleep(1.0)

    logger.info(f"Work phase expired! Entering blocking phase for {block_min} minutes...")
    if do_alert:
        show_osd_notification(
            title=f"{rule.name} Blocker",
            message=f"🔒 Время вышло! Блокировка {rule.name} на {block_min} минут.",
            duration_sec=7.0,
            play_sound=True
        )

    run_blocking_loop(rule=rule, duration_sec=block_min * 60, poll_interval_sec=1.0)
    logger.info(f"=== Session Finished: {rule.name} ===")


# ===== Универсальный контроллер фоновых сессий (для GUI) =====

class SessionState:
    STOPPED = "STOPPED"
    IDLE = "STOPPED"
    WORK_PHASE = "WORK_PHASE"
    BLOCK_PHASE = "BLOCK_PHASE"


class SessionController:
    """Управляет полным циклом сессии фокусировки в фоновом потоке с сохранением состояния."""

    def __init__(self):
        self.state = SessionState.STOPPED
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.session_name = ""
        self.remaining_sec = 0
        self.total_phase_sec = 0
        self.allow_min = 0
        self.block_min = 0

    def is_running(self) -> bool:
        return self.state != SessionState.STOPPED

    def get_seconds_remaining(self) -> int:
        return max(0, int(self.remaining_sec))

    def get_status(self) -> Dict[str, Any]:
        """Возвращает актуальный статус сессии: активность, текущую фазу и секунды до завершения."""
        return {
            "is_active": self.is_running(),
            "state": self.state,
            "remaining_sec": self.get_seconds_remaining(),
            "session_name": self.session_name,
            "allow_min": self.allow_min,
            "block_min": self.block_min
        }

    def stop(self):
        """Останавливает текущую сессию и удаляет сохраненное состояние."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self.state = SessionState.STOPPED
        self.remaining_sec = 0
        clear_session_state()
        logger.info("Session stopped by user.")

    def start_session(
        self,
        rules: Optional[List[AppRule]] = None,
        session_name: str = "Блокировка приложений",
        allow_min: int = 0,
        block_min: int = 25,
        rule_ids: Optional[List[str]] = None,
        do_alert: bool = True,
        target_monitor: str = "auto",
        on_tick: Optional[Callable[[str, int, int], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
        allow_end_time: Optional[float] = None,
        block_end_time: Optional[float] = None,
        **kwargs
    ):
        """Запускает сессию (allow_min -> block_min) в фоновом потоке."""
        rules = rules or []
        self.allow_min = allow_min
        self.block_min = block_min
        with self._lock:
            if self.is_running():
                self.stop()

            now = time.time()
            if allow_end_time is None and block_end_time is None:
                allow_end = now + (allow_min * 60 if allow_min > 0 else 0)
                block_end = allow_end + (block_min * 60)
            else:
                allow_end = allow_end_time if allow_end_time is not None else now
                block_end = block_end_time if block_end_time is not None else (now + block_min * 60)

            # Сохраняем состояние сессии на диск
            state_data = {
                "session_name": session_name,
                "allow_min": allow_min,
                "block_min": block_min,
                "rule_ids": rule_ids or [],
                "allow_end_time": allow_end,
                "block_end_time": block_end,
                "do_alert": do_alert,
                "target_monitor": target_monitor,
                "created_at": now
            }
            save_session_state(state_data)

            self._stop_event.clear()
            self.session_name = session_name
            self._thread = threading.Thread(
                target=self._worker,
                args=(rules, session_name, allow_min, block_min, allow_end, block_end, do_alert, target_monitor, on_tick, on_finish),
                daemon=True
            )
            self._thread.start()

    def restore_if_active(self, rule_resolver_func: Callable[[List[str]], List[AppRule]]) -> Optional[Dict[str, Any]]:
        """
        Проверяет сохраненное состояние сессии.
        Если время сессии еще не истекло, автоматически восстанавливает и возобновляет работу.
        """
        state = load_session_state()
        if not state:
            return None

        now = time.time()
        block_end = state.get("block_end_time", 0)

        if now >= block_end:
            logger.info("Saved session already expired while app was closed. Clearing.")
            clear_session_state()
            return None

        logger.info(f"Restoring active session: '{state.get('session_name')}' (expires at {time.ctime(block_end)})")
        rule_ids = state.get("rule_ids", [])
        rules = rule_resolver_func(rule_ids)

        self.start_session(
            rules=rules,
            session_name=state.get("session_name", "Блокировка приложений"),
            allow_min=state.get("allow_min", 0),
            block_min=state.get("block_min", 50),
            rule_ids=rule_ids,
            do_alert=state.get("do_alert", True),
            target_monitor=state.get("target_monitor", "auto"),
            allow_end_time=state.get("allow_end_time"),
            block_end_time=block_end
        )
        return state

    def _worker(
        self,
        rules: List[AppRule],
        session_name: str,
        allow_min: int,
        block_min: int,
        allow_end: float,
        block_end: float,
        do_alert: bool,
        target_monitor: str,
        on_tick: Optional[Callable[[str, int, int], None]],
        on_finish: Optional[Callable[[], None]]
    ):
        logger.info(f"=== GUI Session Started: '{session_name}' (allow={allow_min}m, block={block_min}m) ===")

        # 1. Фаза разрешенной работы (если allow_min > 0 и еще не истекло время)
        if allow_min > 0 and time.time() < allow_end:
            self.state = SessionState.WORK_PHASE
            allow_total = allow_min * 60
            self.total_phase_sec = allow_total
            alert_shown = False

            while not self._stop_event.is_set() and time.time() < allow_end:
                rem = max(0, int(allow_end - time.time()))
                self.remaining_sec = rem

                if do_alert and not alert_shown and rem <= 60:
                    alert_shown = True
                    show_osd_notification(
                        title=session_name,
                        message="⏳ До блокировки осталась 1 минута!",
                        duration_sec=8.0,
                        play_sound=True,
                        target_monitor=target_monitor
                    )

                if on_tick:
                    try:
                        on_tick(SessionState.WORK_PHASE, rem, allow_total)
                    except Exception:
                        pass

                self._stop_event.wait(1.0)

            if self._stop_event.is_set():
                self.state = SessionState.STOPPED
                clear_session_state()
                return

        # 2. Фаза блокировки (если еще не истекло время block_end)
        if time.time() < block_end:
            self.state = SessionState.BLOCK_PHASE
            block_total = block_min * 60
            self.total_phase_sec = block_total

            if do_alert:
                show_osd_notification(
                    title=session_name,
                    message=f"🔒 Блокировка включена на {block_min} минут.",
                    duration_sec=7.0,
                    play_sound=True,
                    target_monitor=target_monitor
                )

            while not self._stop_event.is_set() and time.time() < block_end:
                close_multiple_rules(rules)
                rem = max(0, int(block_end - time.time()))
                self.remaining_sec = rem

                if on_tick:
                    try:
                        on_tick(SessionState.BLOCK_PHASE, rem, block_total)
                    except Exception:
                        pass

                self._stop_event.wait(1.0)

        self.state = SessionState.STOPPED
        clear_session_state()
        logger.info(f"=== GUI Session Finished: '{session_name}' ===")
        if on_finish and not self._stop_event.is_set():
            try:
                on_finish()
            except Exception:
                pass


# Синглтон контроллера сессий для приложения
session_controller = SessionController()


# ===== Нативная реализация System Tray Icon (Windows) =====

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_STATE = 0x00000008
NIF_INFO = 0x00000010

NIIF_NONE = 0x00000000
NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002
NIIF_ERROR = 0x00000003

WM_USER = 0x0400
WM_TRAYICON = WM_USER + 101
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL


class WindowsTrayIcon:
    """
    Нативная реализация System Tray Icon для Windows без сторонних pip-зависимостей.
    Использует Win32 Shell_NotifyIconW и скрытое окно для приема сообщений трея.
    """

    def __init__(
        self,
        on_click: Optional[Callable[[], None]] = None,
        on_right_click: Optional[Callable[[], None]] = None,
        tooltip: str = "AppBlocker - Управление фокусом",
        icon_path: Optional[str] = None
    ):
        self.on_click = on_click
        self.on_right_click = on_right_click
        self.tooltip = tooltip
        self.icon_path = icon_path

        self.hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._hicon: Optional[int] = None
        self._nid: Optional[NOTIFYICONDATAW] = None
        self._is_running = False
        self._wndproc_ref = None

    def start(self):
        """Запускает поток с окном обработки сообщений трея."""
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._run_tray_thread, daemon=True)
        self._thread.start()

    def _run_tray_thread(self):
        try:
            hinstance = kernel32.GetModuleHandleW(None)
            class_name = f"AppBlockerTrayClass_{int(time.time() * 1000)}"

            # 1. Загрузка иконки
            self._hicon = None
            if self.icon_path and os.path.exists(self.icon_path):
                try:
                    IMAGE_ICON = 1
                    LR_LOADFROMFILE = 0x0010
                    self._hicon = user32.LoadImageW(None, self.icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                except Exception as ex:
                    logger.debug(f"Failed to load icon from {self.icon_path}: {ex}")
                    self._hicon = None

            if not self._hicon:
                default_paths = [
                    get_resource_path(os.path.join("assets", "app_icon.ico")),
                    get_resource_path("app_icon.ico"),
                ]
                for p in default_paths:
                    if os.path.exists(p):
                        try:
                            self._hicon = user32.LoadImageW(None, p, 1, 16, 16, 0x0010)
                            if self._hicon:
                                break
                        except Exception:
                            pass

            if not self._hicon:
                try:
                    IDI_APPLICATION = 32512
                    self._hicon = user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))
                except Exception:
                    pass

            WM_SHOW_APPBLOCKER = user32.RegisterWindowMessageW("AppBlocker_Show_Instance")

            # 2. Оконная процедура
            def _wnd_proc(hwnd, msg, wparam, lparam):
                if msg == WM_TRAYICON:
                    evt = lparam & 0xFFFF
                    if evt in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                        if self.on_click:
                            try:
                                self.on_click()
                            except Exception as ex:
                                logger.error(f"Error in tray click callback: {ex}")
                        return 0
                    elif evt in (WM_RBUTTONUP, WM_CONTEXTMENU):
                        if self.on_right_click:
                            try:
                                self.on_right_click()
                            except Exception as ex:
                                logger.error(f"Error in tray right-click callback: {ex}")
                        return 0
                elif msg == WM_SHOW_APPBLOCKER:
                    if self.on_click:
                        try:
                            self.on_click()
                        except Exception as ex:
                            logger.error(f"Error in show callback: {ex}")
                    return 0
                elif msg == WM_DESTROY:
                    try:
                        user32.PostQuitMessage(0)
                    except Exception:
                        pass
                    return 0

                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            self._wndproc_ref = WNDPROC(_wnd_proc)

            # 3. Регистрация класса окна
            wc = WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = self._wndproc_ref
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinstance
            wc.hIcon = self._hicon
            wc.hCursor = None
            wc.hbrBackground = None
            wc.lpszMenuName = None
            wc.lpszClassName = class_name

            atom = user32.RegisterClassW(ctypes.byref(wc))
            if not atom:
                logger.error(f"Failed to register tray window class. LastError = {kernel32.GetLastError()}")
                return

            # 4. Создание скрытого окна
            self.hwnd = user32.CreateWindowExW(
                0, class_name, "AppBlockerTrayWindow", 0,
                0, 0, 0, 0,
                None, None, hinstance, None
            )

            if not self.hwnd:
                logger.error(f"Failed to create tray window. LastError = {kernel32.GetLastError()}")
                return

            # 5. Регистрация иконки в системном трее
            self._nid = NOTIFYICONDATAW()
            self._nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            self._nid.hWnd = self.hwnd
            self._nid.uID = 1001
            self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            self._nid.uCallbackMessage = WM_TRAYICON
            self._nid.hIcon = self._hicon
            self._nid.szTip = self.tooltip[:127]

            success = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))
            if not success:
                logger.error(f"Shell_NotifyIconW NIM_ADD failed. LastError = {kernel32.GetLastError()}")
            else:
                logger.info("System Tray Icon successfully registered in notification area.")

            # 6. Цикл сообщений Win32
            msg = wintypes.MSG()
            while self._is_running and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        except Exception as ex:
            logger.exception(f"Exception in tray thread: {ex}")
        finally:
            if self._nid and self.hwnd:
                try:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                    logger.info("System Tray Icon removed.")
                except Exception:
                    pass

    def set_tooltip(self, text: str):
        """Обновляет текст подсказки при наведении на иконку в трее."""
        self.tooltip = text
        if self._nid and self.hwnd and self._is_running:
            try:
                self._nid.szTip = text[:127]
                self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
                shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
            except Exception:
                pass

    def show_balloon(self, title: str, message: str):
        """Показывает системный Balloon-баннер над областью уведомлений."""
        if self._nid and self.hwnd and self._is_running:
            try:
                self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
                self._nid.szInfo = message[:255]
                self._nid.szInfoTitle = title[:63]
                self._nid.dwInfoFlags = NIIF_INFO
                shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
            except Exception as ex:
                logger.debug(f"Failed to show balloon: {ex}")

    def stop(self):
        """Удаляет иконку из трея и завершает работу обработчика сообщений."""
        self._is_running = False
        if self._nid and self.hwnd:
            try:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)
            except Exception:
                pass
