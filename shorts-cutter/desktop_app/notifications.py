#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Системное уведомление по завершении скачивания.

Windows - через классический tray-балун (Shell_NotifyIcon с флагом NIF_INFO):
Windows 10/11 сам показывает такой балун как toast в Action Center, никакой
регистрации AUMID/WinRT для этого не нужно (в отличие от "настоящего" toast API,
который для неупакованных win32-приложений капризен). Реализовано на голом
ctypes, без pywin32 - меньше риска сюрпризов при бандлинге PyInstaller-ом.

macOS - через `osascript -e 'display notification ...'`, встроен в систему,
отдельных зависимостей и прав не требует (в отличие от NSUserNotificationCenter
через pyobjc, который на некоторых версиях macOS требует подписанный бандл).
"""

import json
import subprocess
import sys
import threading
import time

_SUBPROCESS_FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def notify(title, message):
    """Best-effort уведомление в фоновом потоке - не блокирует вызывающего и никогда
    не бросает исключений: это второстепенная функция, падать из-за неё нельзя.
    """
    title = (title or "")[:100]
    message = (message or "")[:200]
    if sys.platform == "win32":
        threading.Thread(target=_safe, args=(_notify_windows, title, message), daemon=True).start()
    elif sys.platform == "darwin":
        threading.Thread(target=_safe, args=(_notify_macos, title, message), daemon=True).start()


def _safe(fn, title, message):
    try:
        fn(title, message)
    except Exception:
        pass


def _notify_macos(title, message):
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    subprocess.run(["osascript", "-e", script], check=False, **_SUBPROCESS_FLAGS)


# --- Windows: tray-балун через ctypes (без pywin32/WinRT) ---

def _notify_windows(title, message):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    WNDPROCTYPE = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
    )

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", ctypes.c_uint),
            ("lpfnWndProc", WNDPROCTYPE),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

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
        ]

    NIM_ADD = 0
    NIM_DELETE = 2
    NIF_ICON = 0x2
    NIF_TIP = 0x4
    NIF_INFO = 0x10
    NIIF_INFO = 0x1
    IDI_APPLICATION = 32512
    HWND_MESSAGE = -3

    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]

    def _wndproc(hwnd, msg, wparam, lparam):
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # Ссылка на callback обязана жить весь срок жизни окна - иначе GC соберёт её
    # раньше времени, и первое же оконное сообщение упадёт с access violation.
    wndproc_ref = WNDPROCTYPE(_wndproc)
    hinstance = kernel32.GetModuleHandleW(None)
    class_name = "VideoBustNotifyWnd"

    wc = WNDCLASSW()
    wc.lpfnWndProc = wndproc_ref
    wc.hInstance = hinstance
    wc.lpszClassName = class_name
    user32.RegisterClassW(ctypes.byref(wc))

    hwnd = user32.CreateWindowExW(
        0, class_name, "", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinstance, None,
    )
    if not hwnd:
        return

    try:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_TIP | NIF_INFO
        nid.hIcon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        nid.szTip = "Video Bust"
        # Буферы NOTIFYICONDATAW фиксированного размера (szInfo - 256 WCHAR,
        # szInfoTitle - 64 WCHAR, оба включая завершающий ноль) - слишком длинная
        # строка уронит присваивание с ValueError.
        nid.szInfo = message[:255]
        nid.szInfoTitle = title[:63]
        nid.dwInfoFlags = NIIF_INFO

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        # Балун уже показан и живёт своим таймером в Action Center независимо от
        # владельца - подождать, чтобы он успел появиться, и убрать иконку из трея
        # (этот же поток и создавал окно, и его же удаляет - без кросс-тредовых
        # игр с оконными хендлами).
        time.sleep(5.0)
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
    finally:
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(class_name, hinstance)
