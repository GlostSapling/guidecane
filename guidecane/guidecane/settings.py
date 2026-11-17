# -*- coding: utf-8 -*-
"""运行时参数层: 以 config.py 的大写常量为默认值, 叠加 settings.json 覆盖。
- 各模块用 S.get("NAME") 读取, 每次读取都是最新值 -> Web 改参数可即时生效。
- 少数“仅初始化生效”的参数(串口/波特率/画面尺寸/采样率)改后需重启服务。
线程安全。"""
import json
import os
import threading

import config

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "settings.json")

# 改这些需要重启服务才生效(初始化时读取一次)
RESTART_REQUIRED = {
    "ULTRA_PORT", "ULTRA_PORT_FALLBACK", "ULTRA_BAUD",
    "CAM_INDEX", "CAM_W", "CAM_H", "CAM_FPS",
    "AUDIO_SAMPLE_RATE", "LOOP_HZ", "SCAN_TOPIC",
    "WEB_PORT", "WEB_HOST",
}


def _defaults_from_config():
    d = {}
    for k in dir(config):
        if k.isupper():
            d[k] = getattr(config, k)
    return d


class Settings:
    def __init__(self):
        self._lock = threading.RLock()
        self._d = _defaults_from_config()
        self._defaults = dict(self._d)
        self._load()

    def _load(self):
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    over = json.load(f)
                with self._lock:
                    for k, v in over.items():
                        if k in self._d:
                            self._d[k] = v
            except Exception:
                pass

    def get(self, key, default=None):
        with self._lock:
            return self._d.get(key, default)

    def all(self):
        with self._lock:
            return dict(self._d)

    def defaults(self):
        return dict(self._defaults)

    def set_many(self, updates):
        """更新并持久化。返回实际改动的 {key:value}。做基本类型校验。"""
        changed = {}
        with self._lock:
            for k, v in updates.items():
                if k not in self._d:
                    continue
                cur = self._d[k]
                nv = self._coerce(cur, v)
                if nv is not None and nv != cur:
                    self._d[k] = nv
                    changed[k] = nv
            self._save_locked()
        return changed

    def _coerce(self, cur, v):
        try:
            if isinstance(cur, bool):
                if isinstance(v, str):
                    return v.strip().lower() in ("1", "true", "yes", "on")
                return bool(v)
            if isinstance(cur, int) and not isinstance(cur, bool):
                return int(float(v))
            if isinstance(cur, float):
                return float(v)
            if isinstance(cur, (list, tuple)):
                if isinstance(v, str):
                    v = json.loads(v)
                return [float(x) if isinstance(x, (int, float)) or
                        _isnum(x) else x for x in v]
            if isinstance(cur, dict):
                if isinstance(v, str):
                    v = json.loads(v)
                out = dict(cur)
                for kk, vv in v.items():
                    if isinstance(vv, bool):
                        out[kk] = vv
                    else:
                        out[kk] = float(vv) if _isnum(vv) else vv
                return out
            return str(v)
        except Exception:
            return None

    def _save_locked(self):
        # 只存与默认值不同的项, 保持文件精简
        over = {k: v for k, v in self._d.items() if v != self._defaults.get(k)}
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(over, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)

    def reset(self):
        with self._lock:
            self._d = dict(self._defaults)
            if os.path.exists(SETTINGS_PATH):
                os.remove(SETTINGS_PATH)


def _isnum(x):
    try:
        float(x)
        return True
    except Exception:
        return False


# 全局单例
S = Settings()
