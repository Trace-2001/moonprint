"""本地网页服务。

刻意不依赖 Flask/FastAPI —— 只用标准库 http.server，
这样打包分发时不必多装依赖，换台机器也能直接跑。

接口：
    GET  /api/presets            家人预设列表
    POST /api/preview            只算天文，不渲染（即时反馈公历日期与亮面比例）
    POST /api/render             提交渲染任务 -> {job_id}
    GET  /api/job/<id>           查询进度
    GET  /api/job/<id>/image     取回 PNG（内联）
    GET  /api/job/<id>/download  下载 PNG（附件）
"""

import io
import json
import os
import re
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import pipeline, presets

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def logo_path(name):
    """把 logo 名解析为 web 资源路径。非法名返回 None。"""
    import re as _re
    if not name:
        return None
    if not _re.fullmatch(r"[A-Za-z0-9_-]+", str(name)):
        return None
    p = os.path.join(WEB_DIR, f"logo-moonprint-{name}.png")
    return p if os.path.isfile(p) else None

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

JOBS = {}
_LOCK = threading.Lock()
MAX_JOBS = 8  # 出图体积大，只保留最近若干个，避免内存堆积

_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename(name, default="月相图.png"):
    """保留中文，剔除路径分隔符与控制字符，确保 .png 后缀。"""
    name = re.sub(r"\s+", " ", _BAD_CHARS.sub("_", str(name or "")).strip().strip(". "))
    if len(name) > 80:
        name = name[:80]
    if not name:
        return default
    return name if name.lower().endswith(".png") else name + ".png"


def _evict():
    """超出上限时，丢掉最旧的已完成任务的图像数据。"""
    with _LOCK:
        done = [k for k, v in JOBS.items() if v.get("status") in ("done", "error")]
        if len(JOBS) > MAX_JOBS:
            for k in done[: max(0, len(JOBS) - MAX_JOBS)]:
                JOBS[k].pop("png", None)
                if JOBS[k].get("status") == "done":
                    JOBS[k]["status"] = "expired"


def _run(job_id, payload):
    try:
        people = payload.get("people") or []
        if not people:
            raise ValueError("请至少添加一个人")
        if len(people) > 12:
            raise ValueError("一次最多 12 人（再多图会看不清，建议分批）")

        quality = payload.get("quality", "high")
        cols = payload.get("cols")
        hour = int(payload.get("hour", 12))

        # 可选落款：默认不加，用户勾选后叠加「月印」logo
        logo = None
        if payload.get("add_logo"):
            logo = logo_path(payload.get("logo") or "trans")
        logo_pos = payload.get("logo_position") or "top-left"

        def prog(done, total, msg):
            with _LOCK:
                j = JOBS.get(job_id)
                if j is not None:
                    j["progress"] = (done / total) if total else 0.0
                    j["message"] = msg

        img, infos = pipeline.build(people, quality=quality, cols=cols,
                                    hour=hour, progress=prog,
                                    logo_path=logo, logo_position=logo_pos)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")

        with _LOCK:
            j = JOBS[job_id]
            j["status"] = "done"
            j["progress"] = 1.0
            j["message"] = "完成"
            j["png"] = buf.getvalue()
            j["people"] = [pipeline.describe(i) for i in infos]
            j["size"] = list(img.size)
            j["filename"] = sanitize_filename(
                payload.get("filename"), pipeline.suggest_filename(infos))
    except Exception as e:
        with _LOCK:
            j = JOBS.get(job_id)
            if j is not None:
                j["status"] = "error"
                j["error"] = f"{type(e).__name__}: {e}"
                j["message"] = "出错了"
    finally:
        _evict()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------- 基础工具 ----------
    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        # 安静一点，只在出错时提示
        pass

    # ---------- GET ----------
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            return self._static("index.html")
        if path.startswith("/api/presets"):
            return self._json({"ok": True, "presets": presets.listing()})
        if path.startswith("/api/preset/"):
            pid = path.rstrip("/").split("/")[-1]
            p = presets.get(pid)
            if p is None:
                return self._json({"ok": False, "error": "未知预设"}, 404)
            return self._json({"ok": True, "people": p})
        if path.startswith("/api/job/"):
            # /api/job/<id>              -> ['api','job',<id>]
            # /api/job/<id>/image        -> ['api','job',<id>,'image']
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[3] in ("image", "download"):
                return self._job_image(parts[2], parts[3] == "download")
            if len(parts) == 3:
                return self._job_status(parts[2])
        if path == "/api/qualities":
            from . import render as _r
            return self._json({"ok": True, "qualities": [
                {"id": k, "label": v["label"], "R": v["R"]} for k, v in _r.QUALITY.items()]})
        return self._static(path.lstrip("/"))

    def _static(self, rel):
        # 防目录穿越
        rel = os.path.normpath(rel).lstrip("/")
        full = os.path.join(WEB_DIR, rel)
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            return self._json({"ok": False, "error": "not found"}, 404)
        ext = os.path.splitext(full)[1].lower()
        data = open(full, "rb").read()
        self._send(200, data, MIME.get(ext, "application/octet-stream"))

    def _job_status(self, job_id):
        with _LOCK:
            j = JOBS.get(job_id)
            if not j:
                return self._json({"ok": False, "error": "任务不存在"}, 404)
            return self._json({
                "ok": True,
                "status": j["status"],
                "progress": round(j.get("progress", 0.0), 3),
                "message": j.get("message", ""),
                "error": j.get("error"),
                "people": j.get("people"),
                "size": j.get("size"),
                "filename": j.get("filename"),
            })

    def _job_image(self, job_id, as_attachment):
        with _LOCK:
            j = JOBS.get(job_id)
            if not j or j.get("status") != "done":
                return self._json({"ok": False, "error": "图像未就绪"}, 404)
            png = j.get("png")
            if not png:
                return self._json({"ok": False, "error": "图像已被清理，请重新生成"}, 410)
            fname = j.get("filename") or "月相图.png"
        extra = None
        if as_attachment:
            # RFC 5987 编码中文文件名
            from urllib.parse import quote
            extra = {
                "Content-Disposition":
                    f"attachment; filename*=UTF-8''{quote(fname)}"
            }
        self._send(200, png, "image/png", extra)

    # ---------- POST ----------
    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._json({"ok": False, "error": "请求体不是合法 JSON"}, 400)

        try:
            if path == "/api/preview":
                infos = pipeline.summarize(payload.get("people") or [],
                                           int(payload.get("hour", 12)))
                return self._json({"ok": True,
                                   "people": [pipeline.describe(i) for i in infos]})

            if path == "/api/render":
                job_id = uuid.uuid4().hex[:12]
                with _LOCK:
                    JOBS[job_id] = {"status": "running", "progress": 0.0,
                                    "message": "排队中", "created": time.time()}
                t = threading.Thread(target=_run, args=(job_id, payload), daemon=True)
                t.start()
                return self._json({"ok": True, "job_id": job_id})
        except Exception as e:
            return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 400)

        return self._json({"ok": False, "error": "not found"}, 404)


def make_server(host="127.0.0.1", port=8765):
    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="生日月相图 · 网页版")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    a = ap.parse_args(argv)

    srv = make_server(a.host, a.port)
    url = f"http://{a.host}:{a.port}/"
    print(f"生日月相图 · 网页版已启动: {url}")
    print("按 Ctrl+C 停止")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
