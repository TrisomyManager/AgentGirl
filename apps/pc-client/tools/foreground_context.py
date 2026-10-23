"""Foreground process name and fullscreen flag only; no titles or screenshots."""

import json
import platform


def foreground_context(_params):
    if platform.system() != "Windows":
        return {"available": False}
    import ctypes
    from ctypes import wintypes
    from pathlib import PureWindowsPath

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                  ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return {"available": False}
    try:
        size = wintypes.DWORD(32768)
        name = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            return {"available": False}
        process = PureWindowsPath(name.value).name.lower()
    finally:
        kernel32.CloseHandle(handle)

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                    ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    rect = wintypes.RECT()
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    fullscreen = False
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and user32.GetMonitorInfoW(
        user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info)
    ):
        fullscreen = (rect.left <= info.monitor.left and rect.top <= info.monitor.top
                      and rect.right >= info.monitor.right and rect.bottom >= info.monitor.bottom)
    return {
        "available": True, "foreground_app": process, "fullscreen": fullscreen,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(foreground_context({})))
    except Exception:
        print(json.dumps({"available": False}))
