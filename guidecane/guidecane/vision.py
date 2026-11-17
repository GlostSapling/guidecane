# -*- coding: utf-8 -*-
"""视觉识别: 抓一帧发给 qwen3-vl-flash, 简短描述前方主要物体。
仅在用户触发时调用(Web 按钮/预留物理按钮), 不用于实时避障。
stdlib urllib 调 OpenAI 兼容接口, 无第三方依赖。API Key 由 apikey 读取。"""
import base64
import json
import urllib.request

import apikey
from settings import S


def describe(jpeg_bytes):
    """输入 JPEG 字节, 返回 (text, error)。成功时 error=None。"""
    if not jpeg_bytes:
        return None, "no frame"
    key = apikey.load_key()
    if not key:
        return None, "no api key"
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    data_url = "data:image/jpeg;base64," + b64
    payload = {
        "model": S.get("VISION_MODEL"),
        "max_tokens": int(S.get("VISION_MAX_TOKENS")),
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": S.get("VISION_PROMPT")},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
    }
    req = urllib.request.Request(
        S.get("VISION_API_URL"), data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    try:
        to = float(S.get("VISION_TIMEOUT_S"))
        with urllib.request.urlopen(req, timeout=to) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
        text = obj["choices"][0]["message"]["content"]
        if isinstance(text, list):     # 兼容 content 为分段数组
            text = "".join(seg.get("text", "") for seg in text
                           if isinstance(seg, dict))
        text = (text or "").strip()
        return (text, None) if text else (None, "empty response")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8")[:200]
        except Exception:
            detail = ""
        return None, "http %d %s" % (e.code, detail)
    except Exception as e:
        return None, str(e)[:200]
