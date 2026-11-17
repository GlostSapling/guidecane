# -*- coding: utf-8 -*-
"""读取 DashScope API Key: 优先环境变量 DASHSCOPE_API_KEY, 否则读同目录
secrets.env(格式 DASHSCOPE_API_KEY=sk-...)。Key 不写入代码库。"""
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SECRETS = os.path.join(_BASE_DIR, "secrets.env")


def load_key():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if key:
        return key.strip()
    try:
        with open(_SECRETS, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DASHSCOPE_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None
