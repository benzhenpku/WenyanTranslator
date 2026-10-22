#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文言发信助手 — 启动入口。"""

import sys
import os

# 确保项目根目录在 sys.path 中，以便 src 包可以被导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from src.gui import WenyanTranslatorApp
from src.config_store import write_config


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
