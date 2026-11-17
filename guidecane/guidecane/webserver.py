# -*- coding: utf-8 -*-
"""导盲杖 Web 控制台 (stdlib http.server, 无第三方依赖)。
提供: 实时状态、全部参数查看/编辑、雷达极坐标可视化与朝向标定、语音测试。
挂在主节点上, 通过 ctx 读取实时数据。局域网无鉴权, 勿暴露公网。"""
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from settings import S

_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


class _Handler(BaseHTTPRequestHandler):
    ctx = None                    # 由 start_web 注入

    def log_message(self, *a):    # 静音访问日志
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # ---------------- GET ----------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self._serve_file("app.js", "application/javascript; charset=utf-8")
        if path == "/style.css":
            return self._serve_file("style.css", "text/css; charset=utf-8")
        if path == "/api/status":
            return self._send(200, self.ctx.status())
        if path == "/api/scan":
            return self._send(200, self.ctx.scan())
        if path == "/api/camera.jpg":
            q = {}
            if "?" in self.path:
                for kv in self.path.split("?", 1)[1].split("&"):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        q[k] = v
            jpg = self.ctx.camera_jpeg(q.get("view", "normal"))
            if jpg is None:
                return self._send(503, {"error": "no frame"})
            return self._send(200, jpg, "image/jpeg")
        if path == "/api/params":
            return self._send(200, self.ctx.params())
        self._send(404, {"error": "not found"})

    def _serve_file(self, name, ctype):
        p = os.path.join(_WEB_DIR, name)
        try:
            with open(p, "rb") as f:
                self._send(200, f.read().decode("utf-8"), ctype)
        except FileNotFoundError:
            self._send(404, {"error": "missing " + name})

    # ---------------- POST ----------------
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        body = self._read_json()
        if path == "/api/params":
            changed = S.set_many(body.get("params", {}))
            self.ctx.on_settings_changed()
            return self._send(200, {"changed": changed,
                                    "restart_required": self.ctx.restart_hits(changed)})
        if path == "/api/calibrate":
            # {"dir":"front"/"left"/"right", "angle": <deg>}  (angle 省略=用当前雷达最近点)
            d = body.get("dir")
            angle = body.get("angle", None)
            if angle is None:
                angle = self.ctx.nearest_angle()
            key = {"front": "LIDAR_FRONT_ANGLE_DEG",
                   "left": "LIDAR_LEFT_ANGLE_DEG",
                   "right": "LIDAR_RIGHT_ANGLE_DEG"}.get(d)
            if not key or angle is None:
                return self._send(400, {"error": "bad dir or no scan"})
            changed = S.set_many({key: float(angle)})
            self.ctx.on_settings_changed()
            return self._send(200, {"changed": changed})
        if path == "/api/audio_test":
            self.ctx.audio.play_key(body.get("key", "front_WARN"))
            return self._send(200, {"ok": True})
        if path == "/api/vision":
            return self._send(200, self.ctx.vision_describe(blocking=True))
        if path == "/api/reset":
            S.reset()
            self.ctx.on_settings_changed()
            return self._send(200, {"ok": True})
        if path == "/api/restart":
            threading.Thread(target=_restart_service, daemon=True).start()
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})


def _restart_service():
    try:
        subprocess.run(["sudo", "-n", "systemctl", "restart", "guidecane"],
                       timeout=10)
    except Exception:
        pass


def start_web(ctx):
    if not S.get("WEB_ENABLED"):
        return None
    _Handler.ctx = ctx
    host, port = S.get("WEB_HOST"), int(S.get("WEB_PORT"))
    httpd = ThreadingHTTPServer((host, port), _Handler)
    t = threading.Thread(target=httpd.serve_forever, name="web", daemon=True)
    t.start()
    return httpd
