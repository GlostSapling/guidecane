# -*- coding: utf-8 -*-
"""传感器融合: 把超声波 + 激光雷达 + 摄像头 归并成每个方向的危险级别,
选出最需要报警的目标。距离取“同方向多源的最小值”(最保守/最安全)。"""
from settings import S

_LEVEL_ORDER = {"CLEAR": 0, "CAUTION": 1, "WARN": 2, "DANGER": 3}
_ORDER_LEVEL = {v: k for k, v in _LEVEL_ORDER.items()}


def level_from_cm(cm):
    if cm <= S.get("LEVEL_DANGER_CM"):
        return "DANGER"
    if cm <= S.get("LEVEL_WARN_CM"):
        return "WARN"
    if cm <= S.get("LEVEL_CAUTION_CM"):
        return "CAUTION"
    return "CLEAR"


def _worse(a, b):
    return a if _LEVEL_ORDER[a] >= _LEVEL_ORDER[b] else b


def fuse(ultra, ultra_ok, lidar, lidar_ok, cam_level, cam_ok):
    """返回融合结果 dict:
      dirs: {front,left,right: {"cm":.., "level":..}}
      ground: 摄像头矮障碍级别
      worst: ("front"/"left"/"right"/"ground", level)
    """
    dirs = {}
    maxcm = S.get("LIDAR_MAX_VALID_CM")
    for d in ("front", "left", "right"):
        cm = maxcm
        if ultra_ok and d in ultra:
            cm = min(cm, ultra[d])
        if lidar_ok and d in lidar:
            cm = min(cm, lidar[d])
        dirs[d] = {"cm": cm, "level": level_from_cm(cm)}

    ground = cam_level if cam_ok else "CLEAR"

    # 选最危险目标; 平级时前方优先, 其次地面
    worst_name, worst_level = None, "CLEAR"
    priority = ["front", "ground", "left", "right"]
    candidates = {
        "front": dirs["front"]["level"],
        "left": dirs["left"]["level"],
        "right": dirs["right"]["level"],
        "ground": ground,
    }
    best_rank = -1
    for name in priority:
        lv = candidates[name]
        rank = _LEVEL_ORDER[lv]
        if rank > best_rank:
            best_rank = rank
            worst_name, worst_level = name, lv

    return {"dirs": dirs, "ground": ground, "worst": (worst_name, worst_level)}
