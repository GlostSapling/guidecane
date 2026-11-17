# -*- coding: utf-8 -*-
"""ESP32-S3 超声波读取: 后台线程持续读串口 JSON, 解析 front/left/right(cm)。
每行形如 {"front":99.7,"left":70.8,"right":"empty"}; "empty" -> 视为无障碍。"""
import json
import threading
import time
import os

import serial

import config
from settings import S


class UltrasonicReader:
    def __init__(self):
        self._lock = threading.Lock()
        self._keys = tuple(S.get("ULTRA_KEYS"))
        self._dist = {k: S.get("ULTRA_EMPTY_CM") for k in self._keys}
        self._last_update = 0.0
        self._ser = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ultra", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass

    def _open_port(self):
        port = S.get("ULTRA_PORT")
        if not os.path.exists(port):
            port = S.get("ULTRA_PORT_FALLBACK")
        return serial.Serial(port, int(S.get("ULTRA_BAUD")), timeout=0.2)

    def _handle_line(self, line):
        line = line.strip()
        if not line or not line.startswith("{"):
            return
        try:
            obj = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            return                # 坏行, 跳过
        empty = S.get("ULTRA_EMPTY_CM")
        parsed = {}
        for k in self._keys:
            v = obj.get(k, "empty")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                parsed[k] = float(v)
            else:
                parsed[k] = empty     # "empty"/null/不可测
        with self._lock:
            self._dist.update(parsed)
            self._last_update = time.time()

    def _run(self):
        # 自己按换行切分, 不用 readline() (pyserial 某些版本会抛 TypeError)
        buf = bytearray()
        while not self._stop.is_set():
            try:
                if self._ser is None:
                    self._ser = self._open_port()
                    self._ser.reset_input_buffer()
                    buf.clear()
                n = self._ser.in_waiting or 1
                chunk = self._ser.read(n)
                if chunk:
                    buf.extend(chunk)
                    while b"\n" in buf:
                        raw, _, rest = buf.partition(b"\n")
                        buf = bytearray(rest)
                        self._handle_line(raw.decode("utf-8", "ignore"))
                    if len(buf) > 4096:      # 防坏数据无限增长
                        del buf[:-256]
                else:
                    time.sleep(0.02)
            except (serial.SerialException, OSError, TypeError):
                # 掉线/驱动异常: 关闭重试
                try:
                    if self._ser:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None
                buf.clear()
                time.sleep(1.0)

    def read(self):
        """返回 (dict{front,left,right: cm}, alive:bool)。失效时距离置为无障碍。"""
        with self._lock:
            age = time.time() - self._last_update
            alive = self._last_update > 0 and age <= S.get("ULTRA_TIMEOUT_S")
            if not alive:
                return {k: S.get("ULTRA_EMPTY_CM") for k in self._keys}, False
            return dict(self._dist), True
