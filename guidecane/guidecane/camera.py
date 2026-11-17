# -*- coding: utf-8 -*-
"""斜装单目 RGB 摄像头: 识别地面上的矮小障碍物。
无深度信息, 用启发式: 在“前方地面 ROI”内检测显著边缘/连通块。
本模块被隔离, 日后可用 BPU 目标检测模型替换 detect() 内部。"""
import threading
import time

import cv2
import numpy as np

from settings import S


class CameraDetector:
    def __init__(self):
        self._lock = threading.Lock()
        self._level = "CLEAR"       # CLEAR / CAUTION / WARN / DANGER
        self._ratio = 0.0
        self._last_update = 0.0
        self._frame = None          # 最新 BGR 帧 (供 Web 预览)
        self._cap = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass

    def _open(self):
        cap = cv2.VideoCapture(int(S.get("CAM_INDEX")))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(S.get("CAM_W")))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(S.get("CAM_H")))
        cap.set(cv2.CAP_PROP_FPS, int(S.get("CAM_FPS")))
        return cap

    def _roi_rect(self, w, h):
        x0, y0, x1, y1 = S.get("CAM_ROI")
        return int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)

    def detect(self, frame):
        """返回 (level, edge_ratio)。启发式矮障碍物检测。"""
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = self._roi_rect(w, h)
        roi = frame[y0:y1, x0:x1]
        if roi.size == 0:
            return "CLEAR", 0.0
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, 60, 160)
        ratio = float(np.count_nonzero(edges)) / edges.size

        big_blob = False
        min_area = float(S.get("CAM_MIN_BLOB_AREA"))
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            if cv2.contourArea(c) >= min_area:
                big_blob = True
                break

        warn = float(S.get("CAM_EDGE_RATIO_WARN"))
        danger = float(S.get("CAM_EDGE_RATIO_DANGER"))
        if ratio >= danger and big_blob:
            return "DANGER", ratio
        if ratio >= warn and big_blob:
            return "WARN", ratio
        if ratio >= warn:
            return "CAUTION", ratio
        return "CLEAR", ratio

    def _run(self):
        while not self._stop.is_set():
            period = 1.0 / max(1.0, float(S.get("CAM_FPS")))
            try:
                if self._cap is None:
                    self._cap = self._open()
                    if not self._cap.isOpened():
                        self._cap = None
                        time.sleep(1.0)
                        continue
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    raise IOError("camera read failed")
                level, ratio = self.detect(frame)
                with self._lock:
                    self._level = level
                    self._ratio = ratio
                    self._frame = frame
                    self._last_update = time.time()
                time.sleep(period)
            except Exception:
                try:
                    if self._cap is not None:
                        self._cap.release()
                except Exception:
                    pass
                self._cap = None
                time.sleep(1.0)

    def read(self):
        """返回 (level:str, alive:bool)。"""
        with self._lock:
            age = time.time() - self._last_update
            alive = self._last_update > 0 and age <= S.get("CAM_TIMEOUT_S")
            if not alive:
                return "CLEAR", False
            return self._level, True

    def read_full(self):
        """返回 (level, ratio, alive) 供 Web 显示。"""
        with self._lock:
            age = time.time() - self._last_update
            alive = self._last_update > 0 and age <= S.get("CAM_TIMEOUT_S")
            return self._level, round(self._ratio, 4), alive

    def raw_jpeg(self, quality=80):
        """返回未标注的原始帧 JPEG(供视觉大模型识别)。无帧返回 None。"""
        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame,
                               [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return buf.tobytes() if ok else None

    _LEVEL_BGR = {"CLEAR": (80, 200, 80), "CAUTION": (40, 180, 210),
                  "WARN": (40, 130, 230), "DANGER": (60, 60, 240)}

    def jpeg(self, view="normal", quality=70):
        """返回带标注的 JPEG 字节。view='normal' 画 ROI 框+级别;
        view='edges' 显示 ROI 内的 Canny 边缘图(用于调阈值)。无帧返回 None。"""
        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
            level, ratio = self._level, self._ratio
        if frame is None:
            return None
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = self._roi_rect(w, h)

        if view == "edges":
            roi = frame[y0:y1, x0:x1]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(gray, 60, 160)
            out = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        else:
            out = frame
            color = self._LEVEL_BGR.get(level, (200, 200, 200))
            cv2.rectangle(out, (x0, y0), (x1, y1), color, 2)
            cv2.putText(out, "ROI", (x0 + 4, y0 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            txt = "%s  edge=%.3f" % (level, ratio)
            cv2.rectangle(out, (0, 0), (w, 26), (0, 0, 0), -1)
            cv2.putText(out, txt, (6, 19),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        ok, buf = cv2.imencode(".jpg", out,
                               [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        return buf.tobytes() if ok else None
