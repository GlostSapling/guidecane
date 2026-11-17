# -*- coding: utf-8 -*-
"""导盲杖全局配置。所有可调参数集中在此，方便现场标定。
距离单位统一为厘米(cm)。"""

# ---------------- 超声波 (ESP32-S3, FTDI 串口) ----------------
ULTRA_PORT = "/dev/esp32_ultra"   # udev 稳定符号链接; 回退 /dev/ttyUSB0
ULTRA_PORT_FALLBACK = "/dev/ttyUSB0"
ULTRA_BAUD = 115200
# JSON 字段 -> 逻辑方向; "empty" 表示超量程/不可测, 视为“远处无障碍”
ULTRA_KEYS = ("front", "left", "right")
ULTRA_TIMEOUT_S = 1.0             # 超过此时间无数据则该源判为失效
ULTRA_EMPTY_CM = 999.0            # "empty" 映射的距离(视为无障碍)

# ---------------- 激光雷达 (COIN-D6, ROS2 /scan) ----------------
USE_LIDAR = True
SCAN_TOPIC = "/scan"
# 雷达安装朝向标定: 杖体正前方对应雷达坐标系中的角度(度)。
# COIN-D6 driver: angle -180..180, reversion=true。现场用 test_lidar 标定。
LIDAR_FRONT_ANGLE_DEG = 0.0
LIDAR_LEFT_ANGLE_DEG = 90.0
LIDAR_RIGHT_ANGLE_DEG = -90.0
LIDAR_SECTOR_HALF_DEG = 25.0      # 每个扇区的半张角
LIDAR_MIN_VALID_CM = 5.0          # 小于此值视为噪点丢弃
LIDAR_MAX_VALID_CM = 400.0        # 只关心 4m 内
LIDAR_TIMEOUT_S = 1.0

# ---------------- 摄像头 (斜装单目, 识别矮小障碍物) ----------------
USE_CAMERA = True
CAM_INDEX = 0                     # /dev/video0
CAM_W = 640
CAM_H = 480
CAM_FPS = 15
# 地面感兴趣区(ROI): 图像下半部中央, 归一化坐标 (相机斜向下看前方地面)
CAM_ROI = (0.20, 0.45, 0.80, 0.95)  # (x0,y0,x1,y1) 比例
# 障碍判定: ROI 内边缘密度超过基线的比例阈值
CAM_EDGE_RATIO_WARN = 0.055       # 边缘像素占比 -> 提示
CAM_EDGE_RATIO_DANGER = 0.10      # 边缘像素占比 -> 危险
CAM_MIN_BLOB_AREA = 900           # 最小连通障碍面积(像素)
CAM_TIMEOUT_S = 2.0

# ---------------- 危险分级阈值 (cm) ----------------
# 每个方向按最近障碍距离分级
LEVEL_DANGER_CM = 30.0            # 报警: 极近, 快速急促报警
LEVEL_WARN_CM = 70.0             # 警告: 较近, 中速报警
LEVEL_CAUTION_CM = 110.0         # 注意: 慢速提示
# > CAUTION 视为畅通

# ---------------- 报警音 ----------------
AUDIO_ENABLED = True
AUDIO_ALSA_DEVICE = "default"
AUDIO_SAMPLE_RATE = 16000
AUDIO_VOLUME = 0.6                # 0..1
# 播报方式: "tts"=本地语音, "tone"=纯音提示
AUDIO_MODE = "tts"
# 静音模式(主开关): True 时只保留“危险”级播报(安全底线), 其余全部静音。
AUDIO_MUTE = False
# 各类播报开关(网页“播报开关”面板逐项控制)。某类关掉 -> 该类完全不播(危险也能单独关)。
# 分组: danger=危险(报警) warn=警告 caution=注意 nav=绕行建议 vision=视觉识别
# 默认只开“危险”和“识别”; 警告/注意/绕行默认关(减少啰嗦, 需要时网页单独打开)。
SPEECH_ENABLE = {
    "danger": True,
    "warn": False,
    "caution": False,
    "nav": False,
    "vision": True,
}

# --- TTS 引擎选择 ---
# "qwen"  = 阿里云 qwen3-tts-flash 在线合成(音色最好, 固定短语预渲染缓存后可离线)
# "piper" = 本地神经网络语音(自然, 离线); "espeak" = espeak-ng(机械, 兜底)
# 合成失败自动回退: qwen -> piper -> espeak
TTS_ENGINE = "qwen"
QWEN_TTS_MODEL = "qwen3-tts-flash"
QWEN_TTS_VOICE = "Ethan"         # 男声(可选 Ethan/Dylan/Elias/Cherry...)
# 强制合成语种, 防止自动检测把中文(共用汉字)误读成日语。可选 Chinese/English/...
QWEN_TTS_LANGUAGE = "Chinese"
QWEN_TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_TTS_TIMEOUT_S = 20.0
# piper 模型(相对 guidecane 目录或绝对路径) + 运行方式
PIPER_MODEL = "voices/zh_CN-huayan-medium.onnx"
PIPER_LENGTH_SCALE = 1.0         # >1 更慢更清晰, <1 更快
PIPER_CMD = "python3 -m piper"   # 调用命令(systemd 下 PATH 无 ~/.local/bin)

# --- espeak-ng 参数(TTS_ENGINE="espeak" 时用, 或前两者缺失时回退) ---
TTS_VOICE = "cmn"                # 普通话
TTS_RATE = 160                   # 语速 words/min (80..300)
TTS_PITCH = 50                   # 音调 0..99

# --- 语音播报优先级 (数字越大越优先) ---
# 分类: hazard_<LEVEL> 障碍报警, nav_<action> 绕行建议, vision 视觉识别
SPEECH_PRIORITY = {
    "hazard_DANGER": 100,        # 最高: 可打断正在播的低优先级语音
    "vision": 80,                # 用户主动触发, 高优先
    "hazard_WARN": 70,
    "nav_detour": 50,            # 绕行建议(左前/右前/左转/右转/停)
    "hazard_CAUTION": 25,        # 最低档障碍提示(静音模式默认被屏蔽)
    "nav_forward": 10,           # 前方畅通(基本不播)
}
# 可打断当前播报的最低优先级(仅 DANGER 级会打断, 避免语音被频繁截断)
SPEECH_PREEMPT_PRIO = 100
# 各分类最短重复间隔(秒): 抑制啰嗦
SPEECH_MIN_INTERVAL = {
    "hazard_DANGER": 1.2,
    "hazard_WARN": 3.0,
    "hazard_CAUTION": 6.0,
    "nav_detour": 3.0,
    "nav_forward": 8.0,
    "vision": 1.0,
}
# 各方向+级别的播报文本; {DANGER/WARN/CAUTION}. ground=摄像头矮障碍
TTS_PHRASES = {
    "front_DANGER": "正前方危险",
    "front_WARN": "前方有障碍",
    "front_CAUTION": "注意前方",
    "left_DANGER": "左侧危险",
    "left_WARN": "左侧有障碍",
    "left_CAUTION": "注意左侧",
    "right_DANGER": "右侧危险",
    "right_WARN": "右侧有障碍",
    "right_CAUTION": "注意右侧",
    "ground_DANGER": "注意脚下障碍",
    "ground_WARN": "注意脚下",
    "ground_CAUTION": "留意路面",
}

# --- 纯音(备用) ---
AUDIO_TONE_MS = 120
TONE_FREQ = {                     # 各方向音高(Hz)
    "left": 520.0,
    "front": 780.0,
    "right": 1040.0,
    "ground": 1500.0,
}
# 各危险级别的报警间隔(秒): 越危险越急促
LEVEL_INTERVAL_S = {
    "DANGER": 0.30,
    "WARN": 0.75,
    "CAUTION": 1.60,
}
# 每轮只对“最危险的方向”报警, 避免声音混乱
SPEAK_ONLY_WORST = True

# ---------------- 可行方向导航 (雷达细分区判定绕行) ----------------
# 把前方扇形细分为 5 个方向区, 判断哪个方向"最近障碍够远可通行",
# 在正前方受阻时给出绕行建议(左前/右前绕行、左转/右转、停下)。
NAV_ENABLED = True
NAV_CLEAR_CM = 150.0             # 某方向最近障碍 >= 此值 视为可通行
NAV_ZONE_HALF_DEG = 22.0         # 每个方向区半张角(度)
# 左前/右前区中心 = 正前 与 左/右 的中点; 由雷达朝向标定自动推导
NAV_ANNOUNCE_ONLY_BLOCKED = True # True: 仅正前方不可行时才播报建议
NAV_ANNOUNCE_INTERVAL_S = 3.0    # 同一建议的最短重复间隔(秒)
NAV_PHRASES = {
    "forward": "前方畅通",
    "bear_left": "请左前方绕行",
    "bear_right": "请右前方绕行",
    "turn_left": "请向左转",
    "turn_right": "请向右转",
    "stop": "请停下，前方无法通行",
}

# ---------------- 视觉大模型识别 (qwen3-vl, 偶尔播报前方物体) ----------------
# 用户触发(Web按钮/预留物理按钮)时抓一帧发给 qwen-vl, 简短播报前方物体。
# 不用于实时避障(避障靠超声波/雷达)。API Key 存于 secrets.env, 不入库。
VISION_ENABLED = True
VISION_MODEL = "qwen3-vl-flash"
VISION_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
VISION_TIMEOUT_S = 15.0
VISION_MIN_INTERVAL_S = 3.0       # 两次识别最短间隔, 防连点
VISION_MAX_TOKENS = 60
# 定时自动识别: 每隔 VISION_AUTO_INTERVAL_S 秒自动抓拍播报一次前方物体。
# 0 或 VISION_AUTO_ENABLED=False 关闭。自动播报受静音模式约束(太吵可静音),
# 手动点按钮的识别不受静音限制。
VISION_AUTO_ENABLED = True
VISION_AUTO_INTERVAL_S = 45.0
# 提示词: 要求简短(不超过20字)、只说前方主要物体、面向盲人
VISION_PROMPT = ("你是盲人导航助手。用不超过20个字简短描述这张前方照片里"
                 "最主要的物体或障碍, 只说关键信息, 不要客套, 不要标点堆砌。"
                 "例如: 前方有一把椅子; 右前方是楼梯; 前方是玻璃门。")

# ---------------- 主循环 ----------------
LOOP_HZ = 10.0
LOG_EVERY_N = 20                  # 每 N 帧打印一次状态

# ---------------- Web 界面 ----------------
WEB_ENABLED = True
WEB_HOST = "0.0.0.0"             # 局域网可访问; 无鉴权, 勿暴露公网
WEB_PORT = 8090
