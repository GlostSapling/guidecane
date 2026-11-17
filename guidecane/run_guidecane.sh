#!/bin/bash
# 导盲杖启动脚本: 加载 ROS 环境 -> 启动 bringup launch。
set -e
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=42
export RCUTILS_LOGGING_USE_STDOUT=1
source /opt/ros/humble/setup.bash
if [ -f "$HOME/ros2_ws/install/setup.bash" ]; then
  source "$HOME/ros2_ws/install/setup.bash"
fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec ros2 launch "$HERE/guidecane.launch.py"
