# -*- coding: utf-8 -*-
"""雷达朝向标定辅助: 打印 /scan 中每 30° 扇区的最近距离(cm),
用它确认杖体“正前方”对应雷达坐标系里的哪个角度, 再回填 config.py。
用法: source ROS 环境后 `python3 calibrate_lidar.py`。
在雷达正前方 ~1m 放一个障碍物, 看哪个角度段距离最小 -> 那就是 FRONT 角度。"""
import math
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


def norm(d):
    while d > 180:
        d -= 360
    while d < -180:
        d += 360
    return d


class Cal(Node):
    def __init__(self):
        super().__init__("cal_lidar")
        self.create_subscription(LaserScan, "/scan", self.cb, 10)

    def cb(self, msg):
        buckets = {}
        ang = msg.angle_min
        for i, r in enumerate(msg.ranges):
            deg = norm(math.degrees(ang + i * msg.angle_increment))
            if math.isfinite(r) and 0.05 < r < 4.0:
                b = int(round(deg / 30.0) * 30)
                buckets[b] = min(buckets.get(b, 9e9), r * 100.0)
        line = " ".join("%+4d:%3.0f" % (b, buckets[b])
                        for b in sorted(buckets))
        self.get_logger().info(line if line else "(no returns)")


def main():
    rclpy.init()
    n = Cal()
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass
    n.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
