# -*- coding: utf-8 -*-
"""COIN-D6 激光雷达: 订阅 m1ct_d2 发布的 /scan(LaserScan), 归约为
前/左/右三个扇区的最近距离(cm)。角度朝向从 settings 实时读取, 便于 Web 标定。
同时保留一份降采样的极坐标点云快照, 供 Web 校准可视化。"""
import math
import threading
import time

from sensor_msgs.msg import LaserScan

from settings import S


def _norm_deg(d):
    while d > 180.0:
        d -= 360.0
    while d < -180.0:
        d += 360.0
    return d


class LidarProcessor:
    SECTORS = ("front", "left", "right")

    NAV_ZONES = ("front", "front_left", "front_right", "left", "right")

    def __init__(self, node):
        self._lock = threading.Lock()
        self._sect = {s: S.get("LIDAR_MAX_VALID_CM") for s in self.SECTORS}
        self._nav = {z: S.get("LIDAR_MAX_VALID_CM") for z in self.NAV_ZONES}
        self._last_update = 0.0
        self._snapshot = []       # [(deg, cm), ...] 降采样
        self._sub = node.create_subscription(
            LaserScan, S.get("SCAN_TOPIC"), self._on_scan, 10)

    def _centers(self):
        return {
            "front": float(S.get("LIDAR_FRONT_ANGLE_DEG")),
            "left": float(S.get("LIDAR_LEFT_ANGLE_DEG")),
            "right": float(S.get("LIDAR_RIGHT_ANGLE_DEG")),
        }

    def _nav_centers(self):
        """5 个导航区中心角: 左前/右前 = 正前与左/右的中点。"""
        f = float(S.get("LIDAR_FRONT_ANGLE_DEG"))
        l = float(S.get("LIDAR_LEFT_ANGLE_DEG"))
        r = float(S.get("LIDAR_RIGHT_ANGLE_DEG"))
        return {
            "front": f,
            "front_left": _norm_deg(f + _norm_deg(l - f) / 2.0),
            "front_right": _norm_deg(f + _norm_deg(r - f) / 2.0),
            "left": l,
            "right": r,
        }

    def _on_scan(self, msg):
        half = float(S.get("LIDAR_SECTOR_HALF_DEG"))
        nhalf = float(S.get("NAV_ZONE_HALF_DEG"))
        vmin = float(S.get("LIDAR_MIN_VALID_CM"))
        vmax = float(S.get("LIDAR_MAX_VALID_CM"))
        centers = self._centers()
        ncenters = self._nav_centers()
        mins = {s: math.inf for s in self.SECTORS}
        nmins = {z: math.inf for z in self.NAV_ZONES}
        snap = []
        ang = msg.angle_min
        inc = msg.angle_increment
        n = len(msg.ranges)
        step = max(1, n // 180)   # 快照最多 ~180 点
        for i in range(n):
            r = msg.ranges[i]
            if not math.isfinite(r):
                continue
            cm = r * 100.0
            if not (vmin <= cm <= vmax):
                continue
            deg = _norm_deg(math.degrees(ang + i * inc))
            for s in self.SECTORS:
                if abs(_norm_deg(deg - centers[s])) <= half and cm < mins[s]:
                    mins[s] = cm
            for z in self.NAV_ZONES:
                if abs(_norm_deg(deg - ncenters[z])) <= nhalf and cm < nmins[z]:
                    nmins[z] = cm
            if i % step == 0:
                snap.append((round(deg, 1), round(cm, 1)))
        out = {s: (vmax if math.isinf(mins[s]) else mins[s])
               for s in self.SECTORS}
        navout = {z: (vmax if math.isinf(nmins[z]) else nmins[z])
                  for z in self.NAV_ZONES}
        with self._lock:
            self._sect = out
            self._nav = navout
            self._snapshot = snap
            self._last_update = time.time()

    def read(self):
        with self._lock:
            age = time.time() - self._last_update
            alive = self._last_update > 0 and age <= S.get("LIDAR_TIMEOUT_S")
            if not alive:
                return {s: S.get("LIDAR_MAX_VALID_CM") for s in self.SECTORS}, False
            return dict(self._sect), True

    def snapshot(self):
        """返回 (points[[deg,cm]...], centers{dir:deg}, half, alive)。"""
        with self._lock:
            age = time.time() - self._last_update
            alive = self._last_update > 0 and age <= S.get("LIDAR_TIMEOUT_S")
            return (list(self._snapshot), self._centers(),
                    float(S.get("LIDAR_SECTOR_HALF_DEG")), alive)

    def nav_zones(self):
        """返回 (zones{zone:cm}, alive)。5 个方向区各自最近障碍距离(cm)。"""
        with self._lock:
            age = time.time() - self._last_update
            alive = self._last_update > 0 and age <= S.get("LIDAR_TIMEOUT_S")
            if not alive:
                return ({z: S.get("LIDAR_MAX_VALID_CM")
                         for z in self.NAV_ZONES}, False)
            return (dict(self._nav), True)
