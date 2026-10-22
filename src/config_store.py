#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置读写与日志工具。"""

import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path


# 项目根目录 = src 的父目录
APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "hotkey.log"

_DEFAULT_CONFIG = {
    "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "model": "glm-5.3",
    "api_key": "",
    "default_style": "浅易文言",
    "default_requirements": "",
}


def load_config():
    """从 config.json 读取配置，缺失或损坏时返回默认值。"""
    if not CONFIG_PATH.exists():
        return _DEFAULT_CONFIG.copy()

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            saved_config = json.load(file)
    except (OSError, json.JSONDecodeError):
        return _DEFAULT_CONFIG.copy()

    config = _DEFAULT_CONFIG.copy()
    config.update({key: value for key, value in saved_config.items() if key in _DEFAULT_CONFIG})
    return config


def write_config(config):
    """将配置写入 config.json。"""
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_ccswitch_provider():
    """尝试从 CC Switch 的 SQLite 数据库读取当前 codex provider 配置。"""
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
        from src.core import normalize_endpoint
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


def write_log(message):
    """追加一条带时间戳的日志到 hotkey.log。"""
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass
