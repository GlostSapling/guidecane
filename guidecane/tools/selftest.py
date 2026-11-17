# -*- coding: utf-8 -*-
"""硬件自检: 逐项检查超声波、摄像头、音频, 打印结果。不依赖 ROS。
用法: cd guidecane/guidecane && python3 ../tools/selftest.py"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "guidecane"))
import config  # noqa: E402


def test_ultra():
    from ultrasonic import UltrasonicReader
    r = UltrasonicReader()
    r.start()
    print("[超声波] 等待 3s 数据...")
    time.sleep(3)
    dist, ok = r.read()
    r.stop()
    print("  alive=%s dist=%s" % (ok, dist))
    return ok


def test_camera():
    if not config.USE_CAMERA:
        print("[摄像头] 已禁用")
        return True
    from camera import CameraDetector
    c = CameraDetector()
    c.start()
    print("[摄像头] 等待 3s...")
    time.sleep(3)
    level, ok = c.read()
    c.stop()
    print("  alive=%s level=%s" % (ok, level))
    return ok


def test_audio():
    if not config.AUDIO_ENABLED:
        print("[音频] 已禁用")
        return True
    from audio import AudioAlerter
    a = AudioAlerter()
    print("[音频] 依次播放 左/前/右/地面 提示音...")
    a.beep_test()
    time.sleep(0.5)
    print("  已发送播放请求 (听喇叭确认)")
    return True


if __name__ == "__main__":
    results = {}
    results["ultra"] = test_ultra()
    results["camera"] = test_camera()
    results["audio"] = test_audio()
    print("\n=== 自检结果 ===")
    for k, v in results.items():
        print("  %-8s %s" % (k, "OK" if v else "FAIL"))
