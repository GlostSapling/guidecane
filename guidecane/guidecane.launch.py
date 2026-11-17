# -*- coding: utf-8 -*-
"""导盲杖 bringup: 启动 COIN-D6 雷达驱动(m1ct_d2) + 导盲杖主程序。
复用车上已编译好的 m1ct_d2 驱动, 不重写雷达协议。"""
import os
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import ExecuteProcess

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "guidecane", "main.py")


def generate_launch_description():
    return LaunchDescription([
        # 1) COIN-D6 雷达驱动 -> 发布 /scan (口=/dev/sc_mini)
        Node(
            package="m1ct_d2", executable="m1ct_d2", name="m1ct_d2",
            output="screen",
        ),
        # 2) 导盲杖主程序 (读超声波/摄像头 + 订阅 /scan + 报警音)
        ExecuteProcess(
            cmd=["python3", "-u", APP],   # -u: 无缓冲, 保证日志在 systemd 下实时刷新
            cwd=os.path.join(HERE, "guidecane"),
            output="screen",
        ),
    ])
