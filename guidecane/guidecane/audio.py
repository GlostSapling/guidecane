# -*- coding: utf-8 -*-
"""报警播报 + 语音优先级仲裁。
合成引擎(TTS_ENGINE): "qwen"(在线 qwen3-tts-flash, 音色最好) / "piper"(本地神经网络)
/ "espeak"(兜底)。固定短语预渲染成 WAV 缓存(qwen 结果缓存后离线可用),
aplay 异步播放。所有播报统一经 _submit 仲裁: 按优先级 + 静音模式 + 分类最短间隔
过滤, 仅最高级(DANGER)可打断正在播的语音。"""
import hashlib
import json
import os
import shlex
import subprocess
import threading
import time
import urllib.request
import wave

import numpy as np

import apikey
from settings import S

_CACHE_DIR = "/tmp/guidecane_tts"
# guidecane 目录(用于解析 piper 模型相对路径)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _render_tone(path, freq, ms, sr, vol):
    n = int(sr * ms / 1000.0)
    t = np.linspace(0.0, ms / 1000.0, n, endpoint=False)
    data = np.sin(2.0 * np.pi * freq * t)
    fade = max(1, int(sr * 0.010))
    env = np.ones(n)
    env[:fade] = np.linspace(0.0, 1.0, fade)
    env[-fade:] = np.linspace(1.0, 0.0, fade)
    samples = (data * env * vol * 32767.0).astype("<i2")
    w = wave.open(path, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(samples.tobytes()); w.close()


class AudioAlerter:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._tts_files = {}      # key -> wav path
        self._tone_files = {}
        self._tts_sig = None      # 语音参数指纹, 变了就重渲染
        self._rendering = False
        self._cur_prio = 0        # 正在播放的优先级(用于抢占判断)
        self._cat_last = {}       # category -> (last_time, last_dedup_key)
        os.makedirs(_CACHE_DIR, exist_ok=True)
        self._render_tones()
        self._ensure_tts()

    # ---------- 短语集合(报警 + 导航) ----------
    def _all_phrases(self):
        d = dict(S.get("TTS_PHRASES"))
        d.update(S.get("NAV_PHRASES") or {})
        return d
    # ---------- 渲染 ----------
    def _render_tones(self):
        sr = int(S.get("AUDIO_SAMPLE_RATE"))
        vol = float(S.get("AUDIO_VOLUME"))
        ms = int(S.get("AUDIO_TONE_MS"))
        for name, freq in S.get("TONE_FREQ").items():
            p = os.path.join(_CACHE_DIR, "tone_%s.wav" % name)
            _render_tone(p, float(freq), ms, sr, vol)
            self._tone_files[name] = p

    def _tts_signature(self):
        return "|".join(str(x) for x in (
            S.get("TTS_ENGINE"), S.get("QWEN_TTS_MODEL"), S.get("QWEN_TTS_VOICE"),
            S.get("QWEN_TTS_LANGUAGE"),
            S.get("PIPER_MODEL"), S.get("PIPER_LENGTH_SCALE"),
            S.get("TTS_VOICE"), S.get("TTS_RATE"), S.get("TTS_PITCH")))

    def _piper_model_path(self):
        m = S.get("PIPER_MODEL")
        return m if os.path.isabs(m) else os.path.join(_BASE_DIR, m)

    def _cache_path(self, key, text, sig=None):
        sig = sig or self._tts_signature()
        h = hashlib.md5(sig.encode("utf-8")).hexdigest()[:6]
        th = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
        return os.path.join(_CACHE_DIR, "tts_%s_%s_%s.wav" % (key, th, h))
    # ---------- 合成 (qwen -> piper -> espeak 回退) ----------
    def _synth_qwen(self, text, path):
        key = apikey.load_key()
        if not key:
            return False
        payload = {"model": S.get("QWEN_TTS_MODEL"),
                   "input": {"text": text, "voice": S.get("QWEN_TTS_VOICE")}}
        lang = S.get("QWEN_TTS_LANGUAGE")
        if lang:                     # 固定语种, 防止中文被误判为日语
            payload["input"]["language_type"] = lang
        req = urllib.request.Request(
            S.get("QWEN_TTS_URL"), data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"})
        try:
            to = float(S.get("QWEN_TTS_TIMEOUT_S"))
            with urllib.request.urlopen(req, timeout=to) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
            url = obj["output"]["audio"]["url"]
            with urllib.request.urlopen(url, timeout=to) as a:
                data = a.read()
            with open(path, "wb") as f:
                f.write(data)
            return os.path.getsize(path) > 44
        except Exception:
            return False

    def _synth_piper(self, text, path):
        model = self._piper_model_path()
        if not os.path.exists(model):
            return False
        try:
            cmd = shlex.split(S.get("PIPER_CMD")) + [
                "-m", model,
                "--length-scale", str(float(S.get("PIPER_LENGTH_SCALE"))),
                "-f", path]
            subprocess.run(cmd, input=text.encode("utf-8"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=30, check=True)
            return os.path.exists(path)
        except Exception:
            return False

    def _synth_espeak(self, text, path):
        try:
            amp = int(max(0, min(200, float(S.get("AUDIO_VOLUME")) * 200)))
            subprocess.run(
                ["espeak-ng", "-v", S.get("TTS_VOICE"),
                 "-s", str(int(S.get("TTS_RATE"))),
                 "-p", str(int(S.get("TTS_PITCH"))),
                 "-a", str(amp), "-w", path, text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10, check=True)
            return os.path.exists(path)
        except Exception:
            return False

    def _synth(self, text, path):
        """合成 text 到 path(wav)。按 TTS_ENGINE 选引擎, 失败依次回退。"""
        engine = S.get("TTS_ENGINE")
        if engine == "qwen":
            return (self._synth_qwen(text, path) or self._synth_piper(text, path)
                    or self._synth_espeak(text, path))
        if engine == "piper":
            return self._synth_piper(text, path) or self._synth_espeak(text, path)
        return self._synth_espeak(text, path)
    # ---------- 固定短语预渲染(后台, 不阻塞启动) ----------
    def _ensure_tts(self):
        sig = self._tts_signature()
        if sig == self._tts_sig:
            return
        with self._lock:
            if self._rendering:
                return
            self._rendering = True
        threading.Thread(target=self._render_all, args=(sig,),
                         daemon=True).start()

    def _render_all(self, sig):
        try:
            files = dict(self._tts_files)
            ok = True
            for key, text in self._all_phrases().items():
                p = self._cache_path(key, text, sig)
                if not os.path.exists(p):
                    if not self._synth(text, p):
                        ok = False
                        continue
                files[key] = p
                self._tts_files = files       # 增量生效
            if ok:
                self._tts_sig = sig
        finally:
            self._rendering = False

    def refresh(self):
        """Web 改参数后调用: 重渲染音调 + (语音参数变化时)重渲染短语。"""
        self._render_tones()
        self._ensure_tts()

    # ---------- 优先级仲裁 ----------
    @staticmethod
    def _enable_group(category):
        """把播报分类映射到“播报开关”面板的分组名。"""
        if category == "hazard_DANGER":
            return "danger"
        if category == "hazard_WARN":
            return "warn"
        if category == "hazard_CAUTION":
            return "caution"
        if category == "vision":
            return "vision"
        return "nav"          # nav_forward / nav_detour 归为“绕行”

    def _muted(self, category):
        """静音开关判断: 该类被单独关掉, 或主静音开启且非危险类 -> 静音。"""
        group = self._enable_group(category)
        if not S.get("SPEECH_ENABLE").get(group, True):
            return True
        if S.get("AUDIO_MUTE") and group != "danger":
            return True
        return False

    def _speakable(self, category, prio, dedup_key, now):
        """播报开关/静音 + 分类最短间隔 + 去重, 判断是否放行。"""
        if not S.get("AUDIO_ENABLED"):
            return False
        if self._muted(category):
            return False
        last_t, last_key = self._cat_last.get(category, (0.0, None))
        interval = float(S.get("SPEECH_MIN_INTERVAL").get(category, 3.0))
        # 相同内容受最短间隔约束; 内容变化(不同 dedup_key)则立即放行
        if dedup_key == last_key and now - last_t < interval:
            return False
        return True

    def _play(self, path, prio):
        """按优先级播放; 仅当新优先级 >= 抢占阈值且不低于当前才打断正在播的。"""
        if not path or not os.path.exists(path):
            return False
        with self._lock:
            busy = self._proc is not None and self._proc.poll() is None
            if busy:
                if not (prio >= int(S.get("SPEECH_PREEMPT_PRIO"))
                        and prio >= self._cur_prio):
                    return False
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            try:
                self._proc = subprocess.Popen(
                    ["aplay", "-q", "-D", S.get("AUDIO_ALSA_DEVICE"), path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._cur_prio = prio
                return True
            except FileNotFoundError:
                return False
    def _submit_key(self, phrase_key, category, prio, dedup_key):
        """播报一条已预渲染短语(缺失则即时补合成)。"""
        now = time.time()
        if not self._speakable(category, prio, dedup_key, now):
            return
        path = self._tts_files.get(phrase_key)
        if not path or not os.path.exists(path):
            text = self._all_phrases().get(phrase_key)
            if not text:
                return
            path = self._cache_path(phrase_key, text)
            if not os.path.exists(path) and not self._synth(text, path):
                return
            self._tts_files[phrase_key] = path
        if self._play(path, prio):
            self._cat_last[category] = (now, dedup_key)

    # ---------- 对外播报接口 ----------
    def alert(self, direction, level, ground=False):
        """障碍报警。level in {DANGER,WARN,CAUTION}; ground=True 用脚下短语。"""
        if level == "CLEAR":
            return
        cat = "hazard_%s" % level
        prio = int(S.get("SPEECH_PRIORITY").get(cat, 50))
        if S.get("AUDIO_MODE") != "tts":
            now = time.time()
            name = "ground" if ground else direction
            if self._speakable(cat, prio, name, now):
                p = self._tone_files.get(name, self._tone_files.get("front"))
                if p and self._play(p, prio):
                    self._cat_last[cat] = (now, name)
            return
        key = "%s_%s" % ("ground" if ground else direction, level)
        self._submit_key(key, cat, prio, dedup_key=key)

    def announce_nav(self, action, front_blocked):
        """绕行建议。NAV_ANNOUNCE_ONLY_BLOCKED=True 时仅正前受阻才播。"""
        if not action:
            return
        if S.get("NAV_ANNOUNCE_ONLY_BLOCKED") and not front_blocked:
            return
        cat = "nav_forward" if action == "forward" else "nav_detour"
        prio = int(S.get("SPEECH_PRIORITY").get(cat, 40))
        self._submit_key(action, cat, prio, dedup_key=action)

    def speak_text(self, text, category="vision", prio=None, bypass_mute=True):
        """播报任意动态文本(如视觉识别结果), 即时合成并缓存。"""
        if not text or not S.get("AUDIO_ENABLED"):
            return False
        if prio is None:
            prio = int(S.get("SPEECH_PRIORITY").get(category, 60))
        # 用户主动触发(按钮)默认忽略静音/开关; 定时自动播报受其约束
        if not bypass_mute and self._muted(category):
            return False
        key = "dyn_" + hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
        path = self._cache_path(key, text)
        if not os.path.exists(path) and not self._synth(text, path):
            return False
        ok = self._play(path, prio)
        if ok:
            self._cat_last[category] = (time.time(), text)
        return ok

    # ---------- 测试(Web 按钮): 忽略静音/间隔, 强制播放 ----------
    def play_key(self, key):
        if S.get("AUDIO_MODE") != "tts":
            name = key.split("_")[0]
            return self._play(self._tone_files.get(
                name, self._tone_files.get("front")), 999)
        path = self._tts_files.get(key)
        if not path or not os.path.exists(path):
            text = self._all_phrases().get(key)
            if text:
                path = self._cache_path(key, text)
                if not os.path.exists(path):
                    self._synth(text, path)
                self._tts_files[key] = path
        self._play(path, 999)
