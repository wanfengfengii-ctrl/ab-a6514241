import json
import threading
import unittest
import urllib.error
import urllib.request

from app.server import create_server

VALID_PAYLOAD = {
    "segments": [
        {"id": 1, "scales": [100, 110, 120, 130, 140],
         "types": ["major", "minor", "intermediate", "minor", "major"]},
        {"id": 2, "scales": [105, 115, 125, 135, 150],
         "types": ["minor", "intermediate", "minor", "major", "major"]},
        {"id": 3, "scales": [98, 108, 118, 128, 138],
         "types": ["intermediate", "minor", "major", "minor", "intermediate"]},
    ]
}


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url(path), timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def post(self, path, payload, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url(path), data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    # ---------- 基础端点 ----------

    def test_health(self):
        status, data = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

    def test_meta(self):
        status, data = self.get("/api/meta")
        self.assertEqual(status, 200)
        self.assertEqual(data["limits"],
                         {"minSegments": 3, "maxSegments": 6,
                          "minMarks": 4, "maxMarks": 10})
        self.assertEqual(data["types"], ["major", "intermediate", "minor"])

    def test_index_page_served(self):
        with urllib.request.urlopen(self.url("/"), timeout=5) as resp:
            html = resp.read().decode("utf-8")
        self.assertIn("航海测深图拼接裁决", html)

    def test_unknown_route_404(self):
        status, data = self.get("/api/nope")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "NOT_FOUND")

    # ---------- 成功裁决 ----------

    def test_adjudicate_success(self):
        status, data = self.post("/api/adjudicate", VALID_PAYLOAD)
        self.assertEqual(status, 200)
        self.assertEqual(data["order"], [1, 2, 3])
        self.assertEqual(data["totalPairs"], 7)
        self.assertEqual(data["totalError"], 22)
        self.assertEqual(len(data["boundaries"]), 2)
        first = data["boundaries"][0]
        self.assertEqual((first["left"], first["right"]), (1, 2))
        self.assertEqual(first["delta"], -5)
        self.assertEqual(first["pairCount"], len(first["pairs"]))
        self.assertEqual(data["totalPairs"],
                         sum(b["pairCount"] for b in data["boundaries"]))
        self.assertEqual(data["totalError"],
                         sum(abs(b["delta"]) for b in data["boundaries"]))
        unpaired = {seg["id"]: seg["marks"] for seg in data["unpaired"]}
        self.assertEqual([m["value"] for m in unpaired[1]], [100])
        self.assertEqual([m["value"] for m in unpaired[2]], [150])
        self.assertEqual([m["value"] for m in unpaired[3]], [128, 138])

    # ---------- 录入校验：首个原因 ----------

    def assert_invalid(self, payload, code, message_part):
        status, data = self.post("/api/adjudicate", payload)
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], code)
        self.assertIn(message_part, data["error"]["message"])

    def test_invalid_json(self):
        status, data = self.post("/api/adjudicate", None, raw=b"{not json")
        self.assertEqual(status, 400)
        self.assertEqual(data["error"]["code"], "INVALID_JSON")

    def test_segment_count_bounds(self):
        self.assert_invalid({"segments": VALID_PAYLOAD["segments"][:2]},
                            "INVALID_SEGMENT_COUNT", "3 至 6 段")
        too_many = {"segments": [
            {"id": i, "scales": [1, 2, 3, 4],
             "types": ["major"] * 4} for i in range(1, 8)]}
        self.assert_invalid(too_many, "INVALID_SEGMENT_COUNT", "3 至 6 段")

    def test_invalid_id(self):
        payload = {"segments": [
            {"id": 0, "scales": [1, 2, 3, 4], "types": ["major"] * 4},
            *VALID_PAYLOAD["segments"][1:]]}
        self.assert_invalid(payload, "INVALID_ID", "编号不合法")
        payload["segments"][0]["id"] = 1.5
        self.assert_invalid(payload, "INVALID_ID", "编号不合法")
        payload["segments"][0]["id"] = True
        self.assert_invalid(payload, "INVALID_ID", "编号不合法")

    def test_duplicate_id(self):
        payload = {"segments": [
            {"id": 2, "scales": [1, 2, 3, 4], "types": ["major"] * 4},
            *VALID_PAYLOAD["segments"][1:]]}
        self.assert_invalid(payload, "DUPLICATE_ID", "重复")

    def test_scale_count_bounds(self):
        payload = {"segments": [
            {"id": 1, "scales": [1, 2, 3], "types": ["major"] * 3},
            *VALID_PAYLOAD["segments"][1:]]}
        self.assert_invalid(payload, "INVALID_SCALE_COUNT", "4 至 10 个")

    def test_scale_must_be_int(self):
        payload = {"segments": [
            {"id": 1, "scales": [1, 2, 3, "x"], "types": ["major"] * 4},
            *VALID_PAYLOAD["segments"][1:]]}
        self.assert_invalid(payload, "INVALID_SCALE_VALUE", "须为整数")

    def test_scales_strictly_increasing(self):
        payload = {"segments": [
            {"id": 1, "scales": [1, 2, 2, 4], "types": ["major"] * 4},
            *VALID_PAYLOAD["segments"][1:]]}
        self.assert_invalid(payload, "SCALES_NOT_INCREASING", "严格递增")

    def test_type_count_mismatch(self):
        payload = {"segments": [
            {"id": 1, "scales": [1, 2, 3, 4], "types": ["major"] * 3},
            *VALID_PAYLOAD["segments"][1:]]}
        self.assert_invalid(payload, "TYPE_COUNT_MISMATCH", "不一致")

    def test_type_value_allowed(self):
        payload = {"segments": [
            {"id": 1, "scales": [1, 2, 3, 4],
             "types": ["major", "major", "major", "huge"]},
            *VALID_PAYLOAD["segments"][1:]]}
        self.assert_invalid(payload, "INVALID_TYPE_VALUE", "之一")

    def test_first_error_reported_in_entry_order(self):
        # 第 2 段编号不合法、第 1 段刻度不合法：应报告第 1 段的刻度问题
        payload = {"segments": [
            {"id": 1, "scales": [3, 2, 1, 0], "types": ["major"] * 4},
            {"id": -9, "scales": [1, 2, 3, 4], "types": ["major"] * 4},
            VALID_PAYLOAD["segments"][2]]}
        self.assert_invalid(payload, "SCALES_NOT_INCREASING", "第 1 段")

    # ---------- 无可行拼接 ----------

    def test_infeasible_chain_422(self):
        payload = {"segments": [
            {"id": 1, "scales": [1, 2, 3, 4], "types": ["major"] * 4},
            {"id": 2, "scales": [1, 2, 3, 4], "types": ["minor"] * 4},
            {"id": 3, "scales": [1, 2, 3, 4], "types": ["major"] * 4}]}
        status, data = self.post("/api/adjudicate", payload)
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "NO_FEASIBLE_CHAIN")
        self.assertIn("无法拼成完整刻度链", data["error"]["message"])


if __name__ == "__main__":
    unittest.main()
