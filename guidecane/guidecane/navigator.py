# -*- coding: utf-8 -*-
"""可行方向判定: 基于雷达 5 个方向区(正前/左前/右前/左/右)的最近障碍距离,
判断哪些方向可通行, 并给出绕行建议。超声波的前/左/右会并入对应区(取更近值)。

决策优先级(尽量少偏离正前方):
  正前可行            -> forward   (前方畅通)
  正前不可行, 择优:
    左前可行 & 更宽   -> bear_left (左前方绕行)
    右前可行 & 更宽   -> bear_right(右前方绕行)
    左  可行          -> turn_left (向左转)
    右  可行          -> turn_right(向右转)
    都不可行          -> stop      (停下)
"""
from settings import S

ZONES = ("front", "front_left", "front_right", "left", "right")


def decide(zones, ultra=None, ultra_ok=False):
    """zones: {zone:cm}(雷达)。返回 dict:
      zones: {zone:{"cm":..,"clear":bool}}
      action: NAV_PHRASES 的键
      front_blocked: 正前方是否受阻
      best: 最佳可行方向名
    """
    clear_cm = float(S.get("NAV_CLEAR_CM"))
    maxcm = float(S.get("LIDAR_MAX_VALID_CM"))
    z = {k: min(float(zones.get(k, maxcm)), maxcm) for k in ZONES}

    # 超声波并入(超声波只有前/左/右, 对应 front/left/right 区)
    if ultra_ok and ultra:
        for zk, uk in (("front", "front"), ("left", "left"),
                       ("right", "right")):
            if uk in ultra:
                z[zk] = min(z[zk], float(ultra[uk]))

    clear = {k: (z[k] >= clear_cm) for k in ZONES}
    front_blocked = not clear["front"]

    if clear["front"]:
        action, best = "forward", "front"
    elif clear["front_left"] or clear["front_right"]:
        # 两个斜前方都可行时选更空旷的
        if clear["front_left"] and clear["front_right"]:
            best = ("front_left" if z["front_left"] >= z["front_right"]
                    else "front_right")
        else:
            best = "front_left" if clear["front_left"] else "front_right"
        action = "bear_left" if best == "front_left" else "bear_right"
    elif clear["left"] or clear["right"]:
        if clear["left"] and clear["right"]:
            best = "left" if z["left"] >= z["right"] else "right"
        else:
            best = "left" if clear["left"] else "right"
        action = "turn_left" if best == "left" else "turn_right"
    else:
        action, best = "stop", None

    return {
        "zones": {k: {"cm": round(z[k], 1), "clear": clear[k]} for k in ZONES},
        "action": action,
        "front_blocked": front_blocked,
        "best": best,
    }
