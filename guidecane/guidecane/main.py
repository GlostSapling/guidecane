# -*- coding: utf-8 -*-
"""导盲杖主程序: rclpy 节点 + Web 控制台。
- 后台线程读 ESP32 超声波、摄像头
- 订阅 /scan (COIN-D6 雷达, 由 m1ct_d2 驱动发布)
- 10Hz 融合 -> 选最危险方向 -> 语音/纯音播报
- 内嵌 Web 控制台(参数查看编辑 + 雷达标定)
用法: source ROS 环境后 `python3 main.py`。"""
import math
import sys
import threading
import time

import rclpy
from rclpy.node import Node

from settings import S, RESTART_REQUIRED
from ultrasonic import UltrasonicReader
from camera import CameraDetector
from audio import AudioAlerter
import fusion
import navigator
import vision
import webserver

try:
    from lidar import LidarProcessor
    _HAVE_LIDAR = True
except Exception:
    _HAVE_LIDAR = False


class GuideCane(Node):
    def __init__(self):
        super().__init__("guidecane")
        self.ultra = UltrasonicReader()
        self.ultra.start()

        self.cam = CameraDetector() if S.get("USE_CAMERA") else None
        if self.cam:
            self.cam.start()

        self.lidar = None
        if S.get("USE_LIDAR") and _HAVE_LIDAR:
            self.lidar = LidarProcessor(self)

        self.audio = AudioAlerter()
        self._last = {}           # 最近一次融合结果 (供 Web)
        self._n = 0
        self._vision_lock = threading.Lock()
        self._vision_busy = False
        self._vision_last_t = 0.0
        self._vision_auto_t = time.time()   # 定时自动识别计时起点
        self._vision_last = {"text": None, "error": None, "ts": 0.0}

        self.web = webserver.start_web(self)
        self.get_logger().info(
            "导盲杖启动: 超声波=True 雷达=%s 摄像头=%s 播报=%s Web=%s:%s"
            % (bool(self.lidar), bool(self.cam), S.get("AUDIO_MODE"),
               S.get("WEB_HOST"), S.get("WEB_PORT")))
        self.timer = self.create_timer(1.0 / float(S.get("LOOP_HZ")), self._tick)

    # ---------------- 主循环 ----------------
    def _tick(self):
        ultra, ultra_ok = self.ultra.read()
        lidar, lidar_ok = (self.lidar.read() if self.lidar else ({}, False))
        if self.cam:
            cam_level, cam_ratio, cam_ok = self.cam.read_full()
        else:
            cam_level, cam_ratio, cam_ok = "CLEAR", 0.0, False

        res = fusion.fuse(ultra, ultra_ok, lidar, lidar_ok, cam_level, cam_ok)
        worst_name, worst_level = res["worst"]
        if worst_level != "CLEAR":
            if worst_name == "ground":
                self.audio.alert("front", worst_level, ground=True)
            else:
                self.audio.alert(worst_name, worst_level, ground=False)

        # 可行方向判定 + 绕行建议
        nav = None
        if S.get("NAV_ENABLED") and self.lidar:
            zones, zok = self.lidar.nav_zones()
            if zok:
                nav = navigator.decide(zones, ultra, ultra_ok)
                # 报警优先: 仅在无危险级报警时才播报导航建议, 避免抢话
                if worst_level in ("CLEAR", "CAUTION"):
                    self.audio.announce_nav(nav["action"], nav["front_blocked"])

        # 定时自动视觉识别播报(后台, 不阻塞主循环; 受静音模式约束)
        if (S.get("VISION_ENABLED") and S.get("VISION_AUTO_ENABLED") and self.cam
                and worst_level != "DANGER"):     # 有危险级报警时不抢话
            interval = float(S.get("VISION_AUTO_INTERVAL_S"))
            if interval > 0 and time.time() - self._vision_auto_t >= interval:
                self._vision_auto_t = time.time()
                self.get_logger().info("定时视觉识别: 抓拍播报前方…")
                self.vision_describe(blocking=False, bypass_mute=False)

        # 存快照供 Web
        self._last = {
            "dirs": res["dirs"], "ground": res["ground"],
            "worst": {"dir": worst_name, "level": worst_level},
            "sources": {"ultra": ultra_ok, "lidar": lidar_ok, "camera": cam_ok},
            "ultra_raw": ultra, "lidar_raw": lidar,
            "cam_ratio": cam_ratio, "audio_mode": S.get("AUDIO_MODE"),
            "nav": nav,
            "ts": time.time(),
        }

        self._n += 1
        if self._n % int(S.get("LOG_EVERY_N")) == 0:
            d = res["dirs"]
            self.get_logger().info(
                "F%.0f/%s L%.0f/%s R%.0f/%s 地面=%s | 播报:%s/%s | src[u=%d l=%d c=%d]"
                % (d["front"]["cm"], d["front"]["level"],
                   d["left"]["cm"], d["left"]["level"],
                   d["right"]["cm"], d["right"]["level"],
                   res["ground"], worst_name, worst_level,
                   ultra_ok, lidar_ok, cam_ok))

    # ---------------- Web ctx 接口 ----------------
    def status(self):
        return self._last or {"sources": {}, "dirs": {}}

    def scan(self):
        if not self.lidar:
            return {"alive": False, "points": [], "centers": {}, "half": 0}
        pts, centers, half, alive = self.lidar.snapshot()
        return {"alive": alive, "points": pts, "centers": centers, "half": half}

    def camera_jpeg(self, view="normal"):
        if not self.cam:
            return None
        return self.cam.jpeg(view=view)

    def vision_describe(self, blocking=True, bypass_mute=True):
        """抓一帧发 qwen-vl 识别前方并语音播报。限频, 防连点。
        blocking=True 时同步返回结果 dict(供 Web 按钮直接拿到文本)。
        bypass_mute: 手动触发(按钮)=True 忽略静音; 定时自动=False 受静音约束。"""
        if not S.get("VISION_ENABLED"):
            return {"ok": False, "error": "vision disabled"}
        if not self.cam:
            return {"ok": False, "error": "no camera"}
        now = time.time()
        with self._vision_lock:
            if self._vision_busy:
                return {"ok": False, "error": "busy", "text": None}
            if now - self._vision_last_t < float(S.get("VISION_MIN_INTERVAL_S")):
                return {"ok": False, "error": "too frequent",
                        "text": self._vision_last.get("text")}
            self._vision_busy = True
            self._vision_last_t = now

        def _run():
            text, err = None, None
            try:
                jpg = self.cam.raw_jpeg()
                text, err = vision.describe(jpg)
                if text:
                    self.audio.speak_text(text, category="vision",
                                          bypass_mute=bypass_mute)
                self._vision_last = {"text": text, "error": err,
                                     "ts": time.time()}
            finally:
                self._vision_busy = False
            return text, err

        if blocking:
            text, err = _run()
            return {"ok": bool(text), "text": text, "error": err}
        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "text": None, "error": None, "async": True}

    def vision_last(self):
        return self._vision_last

    def nearest_angle(self):
        """当前雷达最近点的角度(度), 用于一键标定。"""
        if not self.lidar:
            return None
        pts, _, _, alive = self.lidar.snapshot()
        if not alive or not pts:
            return None
        return min(pts, key=lambda p: p[1])[0]

    def params(self):
        cur = S.all()
        return {
            "params": cur,
            "defaults": S.defaults(),
            "restart_required": sorted(RESTART_REQUIRED),
            "tts_keys": sorted(cur.get("TTS_PHRASES", {}).keys()),
        }

    def restart_hits(self, changed):
        return sorted(k for k in changed if k in RESTART_REQUIRED)

    def on_settings_changed(self):
        try:
            self.audio.refresh()
        except Exception:
            pass

    def destroy_node(self):
        try:
            self.ultra.stop()
            if self.cam:
                self.cam.stop()
            if self.web:
                self.web.shutdown()
        except Exception:
            pass
        super().destroy_node()


def main():
    try:
        rclpy.init(args=sys.argv)
    except Exception:
        pass
    node = GuideCane()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
