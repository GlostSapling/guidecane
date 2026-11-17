# 导盲杖软件 (RDK X5)

此目录包含智能导盲杖主程序、Web 控制台、标定工具、启动脚本与 systemd 服务。

完整功能说明、依赖、密钥配置、硬件接线与部署步骤见 [项目 README](../README.md)。

- [实物照片与演示视频](../README.md#图片与视频)
- [技术栈、算法与模块职责](../技术文档.md)
- 前台启动：进入本目录后运行 `./run_guidecane.sh`。
- 板上自检：进入本目录后运行 `python3 tools/selftest.py`。
- 雷达标定：进入本目录后运行 `python3 tools/calibrate_lidar.py`，或使用 Web「雷达标定」。

默认分级阈值为 DANGER ≤ 30 cm、WARN ≤ 70 cm、CAUTION ≤ 110 cm，可在 Web 中修改。
