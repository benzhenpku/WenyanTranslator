#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows API 交互工具：键盘模拟、窗口焦点控制、热键消息结构。"""

import ctypes
import sys


VK_CONTROL = 0x11
VK_A = 0x41
VK_C = 0x43
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002

if sys.platform == "win32":
    KBDLLHOOKSTRUCT = ctypes.c_void_p

    class POINT(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_long),
            ("y", ctypes.c_long),
        ]

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("flags", ctypes.c_ulong),
            ("hwndActive", ctypes.c_void_p),
            ("hwndFocus", ctypes.c_void_p),
            ("hwndCapture", ctypes.c_void_p),
            ("hwndMenuOwner", ctypes.c_void_p),
            ("hwndMoveSize", ctypes.c_void_p),
            ("hwndCaret", ctypes.c_void_p),
            ("rcCaret", RECT),
        ]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_uint),
            ("wParam", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("time", ctypes.c_ulong),
            ("pt", POINT),
        ]

    LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(KBDLLHOOKSTRUCT),
    )

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("union", _INPUTUNION),
        ]

        _anonymous_ = ("union",)


def make_key_input(key_code, key_up):
    """构造一个键盘 INPUT 结构体。"""
    if sys.platform != "win32":
        return None
    input_item = INPUT()
    input_item.type = 1
    input_item.ki.wVk = key_code
    input_item.ki.dwFlags = KEYEVENTF_KEYUP if key_up else 0
    return input_item


def send_key_combo(key_codes):
    """模拟 Ctrl + 一组按键（按下再抬起）。"""
    if sys.platform != "win32":
        return

    inputs = [make_key_input(VK_CONTROL, False)]
    for key_code in key_codes:
        inputs.append(make_key_input(key_code, False))
    for key_code in key_codes:
        inputs.append(make_key_input(key_code, True))
    inputs.append(make_key_input(VK_CONTROL, True))

    input_array = (INPUT * len(inputs))(*inputs)
    ctypes.windll.user32.SendInput(len(inputs), input_array, ctypes.sizeof(INPUT))


def kernel32_current_thread_id():
    """获取当前线程 ID。"""
    if sys.platform != "win32":
        return 0
    return ctypes.windll.kernel32.GetCurrentThreadId()
