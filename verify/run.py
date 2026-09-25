"""一次性验收服务：代码测试 → 构建检查 → API 冒烟。

作为 Compose 中的 verify 服务运行，全部通过后自行退出；
退出码 0 表示验收通过，非 0 表示失败。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
HEALTH_TIMEOUT_SECONDS = int(os.environ.get("VERIFY_HEALTH_TIMEOUT", "90"))

SMOKE_PAYLOAD = {
    "segments": [
        {"id": 1, "scales": [100, 110, 120, 130, 140],
         "types": ["major", "minor", "intermediate", "minor", "major"]},
        {"id": 2, "scales": [105, 115, 125, 135, 150],
         "types": ["minor", "intermediate", "minor", "major", "major"]},
        {"id": 3, "scales": [98, 108, 118, 128, 138],
         "types": ["intermediate", "minor", "major", "minor", "intermediate"]},
    ]
}

INFEASIBLE_PAYLOAD = {
    "segments": [
        {"id": 1, "scales": [1, 2, 3, 4], "types": ["major"] * 4},
        {"id": 2, "scales": [1, 2, 3, 4], "types": ["minor"] * 4},
        {"id": 3, "scales": [1, 2, 3, 4], "types": ["major"] * 4},
    ]
}


def log(message: str) -> None:
    print(f"[verify] {message}", flush=True)


def run_step(name: str, argv: list[str]) -> bool:
    log(f"开始：{name}（{' '.join(argv)}）")
    proc = subprocess.run(argv)
    if proc.returncode != 0:
        log(f"失败：{name}（退出码 {proc.returncode}）")
        return False
    log(f"通过：{name}")
    return True


def http_request(method: str, path: str, payload: dict | None = None,
                 timeout: int = 10):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_BASE + path, data=body, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def wait_for_health() -> bool:
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            status, data = http_request("GET", "/api/health", timeout=5)
            if status == 200 and data.get("status") == "ok":
                log(f"通过：健康检查 {API_BASE}/api/health")
                return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    log(f"失败：{HEALTH_TIMEOUT_SECONDS}s 内服务未就绪（{API_BASE}）")
    return False


def check(condition: bool, name: str) -> bool:
    log(("通过：" if condition else "失败：") + name)
    return condition


def smoke_tests() -> bool:
    ok = True

    status, meta = http_request("GET", "/api/meta")
    ok &= check(status == 200
                and meta.get("types") == ["major", "intermediate", "minor"]
                and meta.get("limits", {}).get("minSegments") == 3,
                "GET /api/meta 返回录入约束")

    status, data = http_request("POST", "/api/adjudicate", SMOKE_PAYLOAD)
    ok &= check(status == 200, "POST /api/adjudicate 成功响应")
    if status != 200:
        return False
    ok &= check(data.get("order") == [1, 2, 3], "拼接顺序为 [1, 2, 3]")
    ok &= check(data.get("totalPairs") == 7, "总配对数为 7")
    ok &= check(data.get("totalError") == 22, "总拼接误差为 22")
    boundaries = data.get("boundaries", [])
    ok &= check(len(boundaries) == 2
                and boundaries[0].get("delta") == -5
                and boundaries[1].get("delta") == -17,
                "边界平移量分别为 -5、-17")
    ok &= check(data.get("totalPairs")
                == sum(b.get("pairCount", 0) for b in boundaries),
                "总配对数与各边界配对数一致")
    unpaired = {seg["id"]: [m["value"] for m in seg["marks"]]
                for seg in data.get("unpaired", [])}
    ok &= check(unpaired.get(1) == [100] and unpaired.get(2) == [150]
                and unpaired.get(3) == [128, 138],
                "未配对刻度与预期一致")

    status, data = http_request("POST", "/api/adjudicate", {
        "segments": [
            {"id": 1, "scales": [1, 2, 2, 4], "types": ["major"] * 4},
            *SMOKE_PAYLOAD["segments"][1:]]})
    ok &= check(status == 400
                and data.get("error", {}).get("code") == "SCALES_NOT_INCREASING",
                "非法刻度返回 400 与首个原因")

    status, data = http_request("POST", "/api/adjudicate", INFEASIBLE_PAYLOAD)
    ok &= check(status == 422
                and data.get("error", {}).get("code") == "NO_FEASIBLE_CHAIN",
                "无可行拼接返回 422")
    return ok


def main() -> int:
    steps_ok = True
    steps_ok &= run_step("代码测试",
                         [sys.executable, "-m", "unittest", "discover",
                          "-s", "tests", "-t", "."])
    steps_ok &= run_step("构建检查（字节码编译）",
                         [sys.executable, "-m", "compileall", "-q",
                          "app", "tests", "verify"])
    steps_ok &= run_step("构建检查（模块导入）",
                         [sys.executable, "-c",
                          "import app.server, app.solver, app.validation"])
    if not wait_for_health():
        steps_ok = False
    else:
        steps_ok &= smoke_tests()

    if steps_ok:
        log("验收全部通过，退出码 0")
        return 0
    log("验收存在失败项，退出码 1")
    return 1


if __name__ == "__main__":
    sys.exit(main())
