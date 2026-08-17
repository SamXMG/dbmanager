# -*- coding: utf-8 -*-
"""routes 层集成测试: 用 stub handler 驱动 monitor/files 路由分发,
覆盖鉴权豁免端点(health/metrics)与安全相关分支(413 请求体上限),
无需真实数据库或网络(P1-5/P2 覆盖率补强, 目标抬升 services+routes 覆盖)。
用法: python tests/test_routes_integration.py
"""

import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 数据层隔离: 指向临时库, 防污染真实 dbmanager.db
_TMP = tempfile.mkdtemp(prefix="dbm_ri_")
os.environ["DBM_DB_FILE"] = os.path.join(_TMP, "dbmanager.db")

import routes.files as rf  # noqa: E402
import routes.monitor as rm  # noqa: E402


def check(name, cond, extra=""):
    if cond:
        print("  ✓", name)
    else:
        print("  ✗", name, extra)
        raise SystemExit("FAILED: " + name)


class _StubHandler:
    """最小 handler stub: 捕获 send_response/send_header/wfile, 提供 _send_json 解析。"""

    def __init__(self):
        self._status = None
        self._headers = []
        self._buf = io.BytesIO()
        self.wfile = self._buf  # handler.wfile.write(...) 约定
        self._json = None
        self.headers = {}
        self.rfile = io.BytesIO(b"")
        self._origin_allowed_ret = False

    def send_response(self, code):
        self._status = code

    def send_header(self, k, v):
        self._headers.append((k, v))

    def end_headers(self):
        pass

    def _send_json(self, code, obj):
        self._status = code
        self._json = obj

    def _body(self):
        return {}

    def _resolve_conn(self):
        return {"database": "test_db"}

    def _origin_allowed(self, origin):
        return self._origin_allowed_ret

    def _audit_action(self, action, detail=""):
        self._audited = (action, detail)


# ---------- 1) monitor: /api/health 探活端点 ----------
def test_monitor_health():
    h = _StubHandler()
    ok = rm.handle_get(h, "/api/health", {})
    check("health 路由命中", ok is True)
    check("health 返回 200", h._status == 200)
    check("health 含 status=ok", h._json and h._json.get("status") == "ok")
    check("health 含 uptime_seconds", "uptime_seconds" in (h._json or {}))
    check("health 含 auth_required 字段", "auth_required" in (h._json or {}))


# ---------- 2) monitor: /api/metrics Prometheus 格式 ----------
def test_monitor_metrics():
    h = _StubHandler()
    ok = rm.handle_get(h, "/api/metrics", {})
    check("metrics 路由命中", ok is True)
    check("metrics 返回 200", h._status == 200)
    body = h._buf.getvalue().decode("utf-8")
    check("metrics 含 dbm_uptime_seconds", "dbm_uptime_seconds" in body)
    check("metrics 含 dbm_requests_total", "dbm_requests_total" in body)
    check("metrics 含 X-Content-Type-Options",
          any(k == "X-Content-Type-Options" for k, _ in h._headers))


# ---------- 3) files: /api/import/xlsx 超 100MB 触发 413 ----------
def test_files_xlsx_too_large():
    h = _StubHandler()
    h.headers = {"Content-Length": str(101 * 1024 * 1024)}
    ok = rf.handle_post(h, "/api/import/xlsx", {})
    check("xlsx 超限路由命中", ok is True)
    check("超 100MB 返回 413", h._status == 413)
    check("413 消息含大小上限提示",
          h._json and "大小上限" in h._json.get("error", ""))


# ---------- 4) files: /api/import/xlsx 正常解析(隔离 ops) ----------
def test_files_xlsx_parse_ok():
    import unittest.mock as mock

    h = _StubHandler()
    h.headers = {"Content-Length": "10"}
    h.rfile = io.BytesIO(b"fake-xlsx-bytes")
    with mock.patch.object(rf, "parse_xlsx_import", return_value=(["c1", "c2"], [["a", "b"]])):
        ok = rf.handle_post(h, "/api/import/xlsx", {})
    check("xlsx 正常路由命中", ok is True)
    check("xlsx 正常返回 200", h._status == 200)
    check("xlsx 返回 header 行", h._json and h._json.get("header") == ["c1", "c2"])
    check("xlsx 返回 rows 行", h._json and h._json.get("rows") == [["a", "b"]])


# ---------- 5) files: /api/import/xlsx 解析异常 -> 400 ----------
def test_files_xlsx_parse_error():
    import unittest.mock as mock

    h = _StubHandler()
    h.headers = {"Content-Length": "10"}
    h.rfile = io.BytesIO(b"bad")
    with mock.patch.object(rf, "parse_xlsx_import", side_effect=ValueError("不是合法 xlsx")):
        ok = rf.handle_post(h, "/api/import/xlsx", {})
    check("xlsx 异常路由命中", ok is True)
    check("xlsx 解析失败返回 400", h._status == 400)
    check("400 消息透出解析错误(业务校验类)",
          h._json and "不是合法 xlsx" in h._json.get("error", ""))


# ---------- 6) files: /api/export/sql 生成 xlsx 下载 ----------
def test_files_export_sql():
    import unittest.mock as mock

    h = _StubHandler()
    with mock.patch.object(rf, "_xlsx_bytes", return_value=b"XLSXBYTES"):
        ok = rf.handle_post(h, "/api/export/sql", {})
    check("export/sql 路由命中", ok is True)
    check("export/sql 返回 200", h._status == 200)
    check("export/sql 写入 xlsx 字节", h._buf.getvalue() == b"XLSXBYTES")


if __name__ == "__main__":
    test_monitor_health()
    test_monitor_metrics()
    test_files_xlsx_too_large()
    test_files_xlsx_parse_ok()
    test_files_xlsx_parse_error()
    test_files_export_sql()
    print()
    print("routes 集成测试全部通过 ✓")
