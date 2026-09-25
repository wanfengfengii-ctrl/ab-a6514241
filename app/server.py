"""HTTP 服务：静态页面 + 业务 API。

路由：
- GET  /api/health      健康检查
- GET  /api/meta        录入约束（段数/刻度数范围、合法刻线类型）
- POST /api/adjudicate  拼接裁决
- GET  /                录入与裁决页面
- GET  /static/*        页面静态资源
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.solver import solve
from app.validation import (ALLOWED_TYPES, MAX_MARKS, MAX_SEGMENTS,
                            MIN_MARKS, MIN_SEGMENTS, ValidationError,
                            parse_segments)

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY_BYTES = 1 << 20  # 1 MiB

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

NO_FEASIBLE_MESSAGE = "任一相邻边界均无合法配对的可行排列：无法拼成完整刻度链"


def solution_to_dict(solution) -> dict:
    return {
        "order": list(solution.order),
        "boundaries": [
            {
                "left": b.left_id,
                "right": b.right_id,
                "delta": b.delta,
                "pairCount": len(b.pairs),
                "pairs": [
                    {"leftValue": p.left_value,
                     "rightValue": p.right_value,
                     "type": p.type}
                    for p in b.pairs
                ],
            }
            for b in solution.boundaries
        ],
        "unpaired": [
            {"id": sid,
             "marks": [{"value": m.value, "type": m.type} for m in marks]}
            for sid, marks in solution.unpaired
        ],
        "totalPairs": solution.total_pairs,
        "totalError": solution.total_error,
    }


class AdjudicatorHandler(BaseHTTPRequestHandler):
    server_version = "DepthChartAdjudicator/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- 基础工具 ----------

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, code: str, message: str,
                    field: str | None = None) -> None:
        error = {"code": code, "message": message}
        if field:
            error["field"] = field
        self._send_json(status, {"error": error})

    def _send_file(self, path: Path) -> None:
        content_type = CONTENT_TYPES.get(path.suffix.lower(),
                                         "application/octet-stream")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 保持简洁的一行访问日志
        print("%s - %s" % (self.address_string(), fmt % args))

    # ---------- GET ----------

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(200, {"status": "ok",
                                  "service": "depth-chart-adjudicator"})
            return
        if path == "/api/meta":
            self._send_json(200, {
                "types": list(ALLOWED_TYPES),
                "limits": {
                    "minSegments": MIN_SEGMENTS,
                    "maxSegments": MAX_SEGMENTS,
                    "minMarks": MIN_MARKS,
                    "maxMarks": MAX_MARKS,
                },
            })
            return
        if path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html")
            return
        if path.startswith("/static/"):
            candidate = (STATIC_DIR / path[len("/static/"):]).resolve()
            if candidate.is_file() and STATIC_DIR in candidate.parents:
                self._send_file(candidate)
                return
            self._send_error(404, "NOT_FOUND", "资源不存在")
            return
        self._send_error(404, "NOT_FOUND", "资源不存在")

    # ---------- POST ----------

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/adjudicate":
            self._send_error(404, "NOT_FOUND", "资源不存在")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_error(400, "INVALID_BODY", "Content-Length 不合法")
            return
        if length > MAX_BODY_BYTES:
            self._send_error(413, "PAYLOAD_TOO_LARGE", "请求体过大")
            return
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_error(400, "INVALID_JSON", "请求体不是合法的 JSON")
            return
        try:
            segments = parse_segments(payload)
        except ValidationError as exc:
            self._send_error(400, exc.code, exc.message, exc.field)
            return
        solution = solve(segments)
        if solution is None:
            self._send_error(422, "NO_FEASIBLE_CHAIN", NO_FEASIBLE_MESSAGE)
            return
        self._send_json(200, solution_to_dict(solution))


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), AdjudicatorHandler)
    httpd.daemon_threads = True
    return httpd


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    httpd = create_server(host, port)
    print(f"depth-chart-adjudicator listening on {host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
