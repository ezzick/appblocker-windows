import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('rcMonitor', RECT),
        ('rcWork', RECT),
        ('dwFlags', wintypes.DWORD)
    ]

MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)

monitors = []
def enum_proc(hMon, hdc, lprc, data):
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if user32.GetMonitorInfoW(hMon, ctypes.byref(mi)):
        r = mi.rcWork
        monitors.append((r.left, r.top, r.right, r.bottom, mi.dwFlags))
    return True

if __name__ == '__main__':
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), MONITORENUMPROC, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.EnumDisplayMonitors(0, None, MONITORENUMPROC(enum_proc), 0)
    print("Detected monitors:", len(monitors))
    for i, m in enumerate(monitors):
        print(f"Monitor {i+1}: Left={m[0]}, Top={m[1]}, Right={m[2]}, Bottom={m[3]}, Flags={m[4]}")