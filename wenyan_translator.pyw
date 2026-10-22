#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A GUI tool that translates modern Chinese into classical Chinese."""

import json
import ctypes
import datetime
import re
import sqlite3
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from tkinter.constants import BOTH, END, LEFT, RIGHT, X, Y


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

STYLES = {
    "浅易文言": "贴近现代语感，清楚易懂，少用生僻字。",
    "典雅文言": "措辞雅洁，结构工整，略带古典韵致。",
    "庄重文言": "语气庄重，句法谨严，适合正式场合。",
    "艰深古奥": "极度仿古，风格晦涩，使用生僻字、古字、异体字和艰深典故，追求先秦两汉到六朝古文的艰涩气韵；但仍需保持句子结构可断读，不使用现代汉语词汇。",
}

SYSTEM_PROMPT = """你是一名精通古今汉语转换的中文编辑。你的唯一任务是把用户提供的现代汉语翻译成流畅自然的文言文。
要求：
1. 只返回译文，不要返回原文、解释、注释、标题、引号、代码块或任何多余前缀。
2. 保留人名、地名、书名、数字、引号、标点等关键信息；专有名词不要随意意译。
3. 保留原文的分段与换行结构，不要合并或重排段落。
4. 根据用户指定的文风调整表达。
5. 对难以直译的现代概念，选择贴合语境的文言表达，必要时可保留原词或用约定俗成的音译。
"""


class TranslationError(Exception):
    pass

VK_CONTROL = 0x11
VK_A = 0x41
VK_C = 0x43
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
LOG_PATH = APP_DIR / "hotkey.log"


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


class WenyanTranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("文言发信助手")
        self.root.geometry("760x720")
        self.root.minsize(620, 580)

        self.config = load_config()
        self.translation_running = False

        self.build_ui()
        self.load_config_into_ui()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=BOTH, expand=True)

        settings_box = ttk.LabelFrame(main, text="接口设置", padding=10)
        settings_box.pack(fill=X)
        settings_box.columnconfigure(1, weight=1)

        ttk.Label(settings_box, text="接口地址").grid(row=0, column=0, sticky="w")
        self.api_url_entry = ttk.Entry(settings_box)
        self.api_url_entry.grid(row=0, column=1, sticky="we", padx=(8, 0), pady=(0, 8))

        ttk.Label(settings_box, text="模型名").grid(row=1, column=0, sticky="w")
        self.model_entry = ttk.Entry(settings_box)
        self.model_entry.grid(row=1, column=1, sticky="we", padx=(8, 0), pady=(0, 8))

        ttk.Label(settings_box, text="API Key").grid(row=2, column=0, sticky="w")
        self.api_key_entry = ttk.Entry(settings_box, show="•")
        self.api_key_entry.grid(row=2, column=1, sticky="we", padx=(8, 0), pady=(0, 8))

        ttk.Label(settings_box, text="默认文风").grid(row=3, column=0, sticky="w")
        self.default_style_combo = ttk.Combobox(settings_box, values=list(STYLES), state="readonly")
        self.default_style_combo.current(0)
        self.default_style_combo.grid(row=3, column=1, sticky="we", padx=(8, 0))

        style_box = ttk.LabelFrame(main, text="本次翻译", padding=10)
        style_box.pack(fill=X, pady=(10, 0))
        style_box.columnconfigure(1, weight=1)

        ttk.Label(style_box, text="文风").grid(row=0, column=0, sticky="w")
        self.request_style_combo = ttk.Combobox(style_box, values=list(STYLES), state="readonly")
        self.request_style_combo.current(0)
        self.request_style_combo.grid(row=0, column=1, sticky="we", padx=(8, 0))

        ttk.Label(style_box, text="补充要求").grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self.requirements_entry = ttk.Entry(style_box)
        self.requirements_entry.grid(row=1, column=1, sticky="we", padx=(8, 0), pady=(8, 0))

        source_box = ttk.LabelFrame(main, text="现代文原文", padding=10)
        source_box.pack(fill=BOTH, expand=True, pady=(10, 0))
        self.source_text = scrolledtext.ScrolledText(
            source_box,
            height=8,
            wrap="word",
            font=("Microsoft YaHei UI", 11),
            undo=True,
        )
        self.source_text.pack(fill=BOTH, expand=True)

        button_frame = ttk.Frame(main)
        button_frame.pack(fill=X, pady=10)
        self.translate_button = ttk.Button(button_frame, text="翻译并复制", command=self.translate)
        self.translate_button.pack(side=LEFT)
        self.copy_button = ttk.Button(button_frame, text="再次复制", command=self.copy_again, state="disabled")
        self.copy_button.pack(side=LEFT, padx=(8, 0))
        self.save_button = ttk.Button(button_frame, text="保存设置", command=self.save_config)
        self.save_button.pack(side=RIGHT)
        self.quick_button = ttk.Button(
            button_frame,
            text="自动翻译剪贴板：关",
            command=self.toggle_clipboard_mode,
        )
        self.quick_button.pack(side=RIGHT, padx=(0, 8))

        result_box = ttk.LabelFrame(main, text="文言文译文", padding=10)
        result_box.pack(fill=BOTH, expand=True)
        self.result_text = scrolledtext.ScrolledText(
            result_box,
            height=8,
            wrap="word",
            font=("Microsoft YaHei UI", 11),
        )
        self.result_text.pack(fill=BOTH, expand=True)

        self.status_var = tk.StringVar(value="请输入现代文，然后点击“翻译并复制”。")
        status_label = ttk.Label(main, textvariable=self.status_var, wraplength=700, foreground="#555555")
        status_label.pack(fill=X, pady=(10, 0))

        self.quick_mode = False
        self.quick_running = False
        self.last_clipboard_text = None
        self.selected_window = None
        self.selected_thread_id = None
        self.selected_attach_success = False
        self.last_chat_window = None
        self.selected_focus_window = None
        self.hotkey_thread = None
        self.hotkey_thread_id = None
        self.hotkey_registered = False
        self.clipboard_before_replacement = None

    def load_config_into_ui(self):
        ccswitch_provider = load_ccswitch_provider()
        if ccswitch_provider:
            self.config.update(ccswitch_provider)

        self.api_url_entry.delete(0, END)
        self.api_url_entry.insert(0, self.config["api_url"])
        self.model_entry.delete(0, END)
        self.model_entry.insert(0, self.config["model"])
        self.api_key_entry.delete(0, END)
        self.api_key_entry.insert(0, self.config["api_key"])

        default_style = self.config["default_style"]
        if default_style in STYLES:
            self.default_style_combo.set(default_style)
            self.request_style_combo.set(default_style)

        if self.config["default_requirements"]:
            self.requirements_entry.insert(0, self.config["default_requirements"])
        write_log("程序启动")

        self.add_context_menu()
        self.root.after(400, self.poll_foreground_window)
        self.root.after(500, self.start_hotkey_background)

    def start_hotkey_background(self):
        self.hotkey_thread = threading.Thread(target=self.hotkey_message_loop, daemon=True)
        self.hotkey_thread.start()

    def hotkey_message_loop(self):
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self.hotkey_thread_id = kernel32.GetCurrentThreadId()
        hotkey_id = 0xB100
        registered = user32.RegisterHotKey(None, hotkey_id, 0x0002 | 0x0001, ord("M"))
        self.hotkey_registered = bool(registered)
        if not registered:
            registered = user32.RegisterHotKey(None, hotkey_id, 0x0002 | 0x0001 | 0x4000, ord("M"))
            self.hotkey_registered = bool(registered)
        write_log(f"启动全局热键注册: {self.hotkey_registered}, 错误码 {ctypes.GetLastError()}")
        if not registered:
            self.root.after(0, lambda: self.set_status("后台模式已启动，但全局热键注册失败。"))
            return

        message = MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == 0x0312 and message.wParam == hotkey_id:
                write_log("全局热键触发")
                self.root.after(0, self.replace_selected_from_chat)

        user32.UnregisterHotKey(None, hotkey_id)

    def add_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="自动替换", command=self.replace_selected_from_chat)

        def show_menu(event):
            self.context_menu.tk_popup(event.x_root, event.y_root)

        self.root.bind("<Button-3>", show_menu)

    def poll_foreground_window(self):
        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            foreground_window = user32.GetForegroundWindow()
            own_window = user32.GetAncestor(self.root.winfo_id(), 2)
            if foreground_window and foreground_window != own_window:
                self.last_chat_window = foreground_window
        self.root.after(400, self.poll_foreground_window)

    def collect_config(self):
        return {
            "api_url": self.api_url_entry.get().strip(),
            "model": self.model_entry.get().strip(),
            "api_key": self.api_key_entry.get(),
            "default_style": self.default_style_combo.get(),
            "default_requirements": self.requirements_entry.get().strip(),
        }

    def save_config(self):
        self.config = self.collect_config()
        write_config(self.config)
        self.set_status("设置已保存。")

    def translate(self):
        if self.translation_running:
            return

        source_text = self.source_text.get("1.0", "end-1c").strip()
        if not source_text:
            self.set_status("请先输入要翻译的现代文。")
            return

        api_url = self.api_url_entry.get().strip()
        model = self.model_entry.get().strip()
        api_key = self.api_key_entry.get().strip()

        if not api_url:
            self.set_status("请填写接口地址。")
            return
        if not model:
            self.set_status("请填写模型名。")
            return
        if not api_key:
            self.set_status("请填写 API Key。")
            return

        style = self.request_style_combo.get()
        requirements = self.requirements_entry.get().strip()

        self.translation_running = True
        self.translate_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.result_text.delete("1.0", END)
        self.set_status("正在翻译，请稍候…")

        thread = threading.Thread(
            target=self.translation_worker,
            args=(api_url, model, api_key, style, requirements, source_text),
            daemon=True,
        )
        thread.start()

    def translation_worker(self, api_url, model, api_key, style, requirements, source_text):
        try:
            result = request_translation(api_url, model, api_key, style, requirements, source_text)
            self.root.after(0, self.translation_finished, result, None)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self.root.after(0, self.translation_finished, None, message)

    def translation_finished(self, result, error):
        self.translation_running = False
        self.translate_button.configure(state="normal")

        if error:
            self.set_status("翻译失败：" + error)
            messagebox.showerror("文言发信助手", "翻译失败：\n" + error)
            return

        self.result_text.delete("1.0", END)
        self.result_text.insert("1.0", result)
        self.copy_to_clipboard(result)
        self.copy_button.configure(state="normal")
        self.set_status("已复制，可粘贴到聊天框。")

    def copy_again(self):
        result = self.result_text.get("1.0", "end-1c").strip()
        if result:
            self.copy_to_clipboard(result)
            self.set_status("已再次复制，可粘贴到聊天框。")

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def set_status(self, message):
        self.status_var.set(message)

    def quick_translate(self, selected_text=None):
        if self.quick_running:
            return

        if selected_text is None:
            try:
                selected_text = self.root.clipboard_get().strip()
            except tk.TclError:
                selected_text = ""

        if not selected_text:
            self.quick_running = False
            self.set_status("剪贴板为空。请先在 QQ/微信复制要翻译的文字。")
            write_log("剪贴板为空")
            return

        api_url = self.api_url_entry.get().strip()
        model = self.model_entry.get().strip()
        api_key = self.api_key_entry.get().strip()
        style = self.request_style_combo.get()
        requirements = self.requirements_entry.get().strip()

        if not api_url or not model or not api_key:
            self.quick_running = False
            self.set_status("快捷键替换失败：请检查接口地址、模型名和 API Key。")
            return

        self.set_status("正在翻译剪贴板内容…")
        write_log(f"开始翻译，长度: {len(selected_text)}")
        thread = threading.Thread(
            target=self.quick_translation_worker,
            args=(api_url, model, api_key, style, requirements, selected_text),
            daemon=True,
        )
        thread.start()

    def quick_translation_worker(self, api_url, model, api_key, style, requirements, selected_text):
        try:
            result = request_translation(api_url, model, api_key, style, requirements, selected_text)
            self.root.after(0, self.quick_translation_finished, result, None)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self.root.after(0, self.quick_translation_finished, None, message)

    def quick_translation_finished(self, result, error):
        if error:
            self.quick_running = False
            self.set_status("快捷键替换失败：" + error)
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(result)
        self.root.update()
        write_log("翻译完成，已写入剪贴板")
        self.quick_running = False
        self.result_text.delete("1.0", END)
        self.result_text.insert("1.0", result)
        self.copy_button.configure(state="normal")
        self.set_status("译文已复制，可回聊天框 Ctrl+V 粘贴发送。")

    def toggle_clipboard_mode(self):
        if self.quick_mode:
            self.quick_mode = False
            self.quick_button.configure(text="自动翻译剪贴板：关")
            self.set_status("自动翻译剪贴板已关闭。")
            write_log("自动翻译剪贴板已关闭")
            return

        if not self.api_url_entry.get().strip() or not self.model_entry.get().strip() or not self.api_key_entry.get().strip():
            self.set_status("请先检查接口地址、模型名和 API Key。")
            return

        self.quick_mode = True
        try:
            self.last_clipboard_text = self.root.clipboard_get()
        except tk.TclError:
            self.last_clipboard_text = None
        self.quick_button.configure(text="自动翻译剪贴板：开")
        self.set_status("自动翻译剪贴板已开启。复制文字后会自动变成文言文。")
        write_log("自动翻译剪贴板已开启")
        self.root.after(600, self.poll_clipboard)

    def remember_selected_window(self):
        if sys.platform != "win32":
            return False

        user32 = ctypes.windll.user32
        self.selected_window = self.last_chat_window
        if not self.selected_window:
            return False

        self.selected_thread_id = user32.GetWindowThreadProcessId(self.selected_window, None)
        thread_info = GUITHREADINFO()
        thread_info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if user32.GetGUIThreadInfo(self.selected_thread_id, ctypes.byref(thread_info)):
            self.selected_focus_window = thread_info.hwndFocus
        else:
            self.selected_focus_window = None

        current_thread_id = kernel32_current_thread_id()
        self.selected_attach_success = False
        self.clipboard_before_replacement = None
        try:
            self.clipboard_before_replacement = self.root.clipboard_get()
        except tk.TclError:
            pass

        if self.selected_thread_id and self.selected_thread_id != current_thread_id:
            self.selected_attach_success = bool(
                user32.AttachThreadInput(current_thread_id, self.selected_thread_id, True)
            )
        return bool(self.selected_window)

    def replace_selected_from_chat(self):
        if self.quick_running:
            return

        if not self.remember_selected_window():
            self.set_status("没有找到要替换的窗口。请在 QQ/微信里选中文字后右键悬浮窗。")
            return

        self.quick_running = True
        self.activate_window(self.selected_window)
        self.root.after(250, self.copy_selected_text)

    def activate_window(self, hwnd):
        if not hwnd:
            return

        user32 = ctypes.windll.user32
        current_thread_id = kernel32_current_thread_id()
        target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        attach_success = False

        if target_thread_id and target_thread_id != current_thread_id:
            attach_success = bool(user32.AttachThreadInput(current_thread_id, target_thread_id, True))

        try:
            user32.ShowWindow(hwnd, 9)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            if attach_success and self.selected_focus_window:
                user32.SetFocus(self.selected_focus_window)
        finally:
            if attach_success:
                user32.AttachThreadInput(current_thread_id, target_thread_id, False)

        write_log(
            f"激活窗口: {hwnd}, 焦点: {self.selected_focus_window}, "
            f"线程: {target_thread_id}, 附加: {attach_success}"
        )

    def copy_selected_text(self):
        write_log("自动替换：尝试发送 Ctrl+C")
        try:
            self.root.clipboard_get()
        except tk.TclError:
            pass

        self.root.clipboard_clear()
        self.root.update()
        send_key_combo((VK_C,))
        write_log("自动替换：已发送 Ctrl+C")
        self.root.after(500, self.read_selected_text)

    def read_selected_text(self):
        try:
            selected_text = self.root.clipboard_get().strip()
        except tk.TclError:
            selected_text = ""

        if not selected_text:
            self.quick_running = False
            if self.clipboard_before_replacement is not None:
                self.root.clipboard_clear()
                self.root.clipboard_append(self.clipboard_before_replacement)
                self.root.update()
            self.selected_window = None
            self.selected_thread_id = None
            self.selected_attach_success = False
            self.set_status("自动替换失败：没有读取到选中文字。")
            write_log("自动替换：未读取到选中文字")
            return

        api_url = self.api_url_entry.get().strip()
        model = self.model_entry.get().strip()
        api_key = self.api_key_entry.get().strip()
        style = self.request_style_combo.get()
        requirements = self.requirements_entry.get().strip()

        if not api_url or not model or not api_key:
            self.quick_running = False
            self.set_status("自动替换失败：请检查接口地址、模型名和 API Key。")
            return

        self.set_status("自动替换：正在翻译…")
        write_log(f"自动替换：开始翻译，长度 {len(selected_text)}")
        thread = threading.Thread(
            target=self.quick_translation_worker_auto,
            args=(api_url, model, api_key, style, requirements, selected_text),
            daemon=True,
        )
        thread.start()

    def quick_translation_worker_auto(self, api_url, model, api_key, style, requirements, selected_text):
        try:
            result = request_translation(api_url, model, api_key, style, requirements, selected_text)
            self.root.after(0, self.quick_translation_finished_auto, result, None)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self.root.after(0, self.quick_translation_finished_auto, None, message)

    def paste_into_selected_window(self):
        self.activate_window(self.selected_window)
        self.root.after(180, lambda: send_key_combo((VK_A,)))
        self.root.after(360, lambda: send_key_combo((VK_V,)))
        self.root.after(650, self.finish_replacement)

    def finish_replacement(self):
        if self.selected_attach_success and self.selected_thread_id:
            ctypes.windll.user32.AttachThreadInput(
                kernel32_current_thread_id(),
                self.selected_thread_id,
                False,
            )

        self.selected_window = None
        self.selected_thread_id = None
        self.selected_attach_success = False
        self.quick_running = False
        if self.clipboard_before_replacement is not None:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.clipboard_before_replacement)
            self.root.update()
            self.clipboard_before_replacement = None
        if self.quick_mode:
            self.root.deiconify()
        self.set_status("自动替换完成。请检查聊天框后发送。")
        write_log("自动替换：完成")

    def quick_translation_finished_auto(self, result, error):
        if error:
            self.quick_running = False
            self.set_status("自动替换失败：" + error)
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(result)
        self.root.update()
        self.result_text.delete("1.0", END)
        self.result_text.insert("1.0", result)
        self.copy_button.configure(state="normal")
        write_log("自动替换：翻译完成，准备粘贴")
        self.root.after(150, self.paste_into_selected_window)

    def poll_clipboard(self):
        if not self.quick_mode:
            return

        try:
            current_text = self.root.clipboard_get()
        except tk.TclError:
            current_text = None

        if (
            current_text
            and current_text.strip()
            and current_text != self.last_clipboard_text
            and current_text != self.result_text.get("1.0", "end-1c")
        ):
            self.last_clipboard_text = current_text
            self.quick_translate(current_text)

        self.root.after(600, self.poll_clipboard)


def request_translation(api_url, model, api_key, style, requirements, source_text):
    endpoint = normalize_endpoint(api_url)
    style_description = STYLES[style]

    user_prompt = f"""文风：{style}
文风说明：{style_description}
补充要求：{requirements or "无"}

现代文原文：
<original_text>
{source_text}
</original_text>
"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "stream": False,
        "reasoning_effort": "high",
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8")
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {}).get("message", error_body)
        except Exception:
            error_message = ""
        raise TranslationError(f"HTTP {exc.code}：{error_message or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise TranslationError("无法连接接口，请检查网络或接口地址。") from exc
    except TimeoutError as exc:
        raise TranslationError("请求超时，请稍后重试。") from exc

    try:
        response_data = json.loads(response_body)
        content = response_data["choices"][0]["message"]["content"].strip()
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise TranslationError("接口返回格式不正确。") from exc

    if not content:
        raise TranslationError("接口返回了空译文。")

    return content


def normalize_endpoint(api_url):
    api_url = api_url.strip().rstrip("/")
    if api_url.endswith("/chat/completions"):
        return api_url
    return api_url + "/chat/completions"


def send_key_combo(key_codes):
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


def make_key_input(key_code, key_up):
    input_item = INPUT()
    input_item.type = 1
    input_item.ki.wVk = key_code
    input_item.ki.dwFlags = KEYEVENTF_KEYUP if key_up else 0
    return input_item


def load_config():
    defaults = {
        "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "model": "glm-5.3",
        "api_key": "",
        "default_style": "浅易文言",
        "default_requirements": "",
    }

    if not CONFIG_PATH.exists():
        return defaults

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            saved_config = json.load(file)
    except (OSError, json.JSONDecodeError):
        return defaults

    config = defaults.copy()
    config.update({key: value for key, value in saved_config.items() if key in defaults})
    return config


def load_ccswitch_provider():
    if sys.platform != "win32":
        return None

    database_path = Path.home() / ".cc-switch" / "cc-switch.db"
    if not database_path.exists():
        return None

    try:
        connection = sqlite3.connect(database_path)
        row = connection.execute(
            "SELECT settings_config FROM providers WHERE app_type = 'codex' AND is_current = 1"
        ).fetchone()
        connection.close()
    except sqlite3.Error:
        return None

    if not row:
        return None

    try:
        provider_config = json.loads(row[0])
        api_key = provider_config["auth"]["OPENAI_API_KEY"].strip()
        toml_config = provider_config["config"]
        base_url_match = re.search(r'base_url\s*=\s*"([^"]+)"', toml_config)
        model_match = re.search(r'^model\s*=\s*"([^"]+)"', toml_config, re.MULTILINE)
        if not api_key or not base_url_match or not model_match:
            return None
        return {
            "api_url": normalize_endpoint(base_url_match.group(1)),
            "model": model_match.group(1),
            "api_key": api_key,
        }
    except (KeyError, TypeError, ValueError):
        return None


def kernel32_current_thread_id():
    return ctypes.windll.kernel32.GetCurrentThreadId()


def write_log(message):
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def write_config(config):
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main():
    root = tk.Tk()
    app = WenyanTranslatorApp(root)

    def on_close():
        app.config = app.collect_config()
        write_config(app.config)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
