# -*- coding: utf-8 -*-
"""P0 安全回归: SSRF 防护 / SQLite 路径沙箱 / X-User-Token 头降级(cookie 优先)。
不依赖真实数据库或网络, 直接对 dbcore / auth 做单元断言。
用法: python tests/test_p0_security.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 数据层隔离: 在 import auth 之前把 DBM_DB_FILE 指到临时库, 防测试污染真实 dbmanager.db
_TMP = tempfile.mkdtemp(prefix="dbm_p0_")
os.environ["DBM_DB_FILE"] = os.path.join(_TMP, "dbmanager.db")

from core import auth   # noqa: E402
from core import config  # noqa: E402
from db import dbcore  # noqa: E402

FAIL = []


def check(name, cond, extra=""):
    """pytest 兼容(2.2): 断言即失败标记, 同时保留 CLI 打印输出"""
    if cond:
        print("  ✓", name)
    else:
        print("  ✗", name, extra)
    assert cond, "%s %s" % (name, extra)


# ---------- 1) is_safe_server (SSRF 防护) ----------
def test_is_safe_server():
    cases = [
        ("mysql.host", True),
        ("192.168.1.10", True),
        ("db.example.com", True),
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("169.254.169.254", False),   # 云元数据(经典 SSRF 靶标)
        ("169.254.1.1", False),        # 链路本地
        ("0.0.0.0", False),            # 监听通配, 非合法目标
        ("fe80::1", False),            # IPv6 链路本地(P2-1 兜底)
        ("fe80::1%eth0", False),       # IPv6 链路本地带 zone
        ("::ffff:169.254.169.254", False),  # IPv4-mapped IPv6 元数据
        ("fd00::1", True),             # IPv6 ULA 内网(放行)
        ("::ffff:192.168.1.5", True),  # IPv4-mapped 内网(放行)
        ("http://169.254.169.254", False),
        ("http://192.168.1.1", False),
        ("/etc/passwd", False),
        ("\\\\host\\share", False),
        ("", False),
    ]
    for srv, exp in cases:
        got = dbcore.is_safe_server(srv)
        check("is_safe_server(%r)=%s" % (srv, got), got == exp,
              "期望 %s 实际 %s" % (exp, got))


# ---------- 2) SQLite 路径沙箱 ----------
def test_sqlite_sandbox():
    config.DATA_ROOT = _TMP
    config.SQLITE_ALLOW_ROOTS = []
    # 相对路径按 cwd 解析(历史约定), 落在 cwd 内即放行
    ok = dbcore._safe_sqlite_path("a.db")
    check("相对路径落在 cwd 内", os.path.dirname(ok) == os.getcwd())
    # 绝对路径落在 DATA_ROOT 内放行
    ok2 = dbcore._safe_sqlite_path(os.path.join(_TMP, "sub", "x.db"))
    check("绝对路径落在 DATA_ROOT 内", os.path.dirname(ok2) == os.path.join(_TMP, "sub"))
    # 路径穿越必须拒绝(逃逸 cwd 与 DATA_ROOT)
    try:
        dbcore._safe_sqlite_path("../../etc/passwd")
        check("拒绝 ../../ 穿越", False, "未抛异常")
    except ValueError:
        check("拒绝 ../../ 穿越", True)
    # DBM_SQLITE_ALLOW_ROOTS 追加根生效
    extra = tempfile.mkdtemp(prefix="dbm_p0_extra_")
    config.SQLITE_ALLOW_ROOTS = [extra]
    ok3 = dbcore._safe_sqlite_path(os.path.join(extra, "y.db"))
    check("额外允许根内路径放行", os.path.dirname(ok3) == extra)


# ---------- 3) build_url 经 SQLite 沙箱触发拒绝 ----------
def test_build_url_sandbox():
    config.DATA_ROOT = _TMP
    config.SQLITE_ALLOW_ROOTS = []
    u = dbcore.build_url({"db_type": "sqlite", "database": "sub/x.db"})
    check("build_url 合法 sqlite 成功", u.startswith("sqlite:///"))
    try:
        dbcore.build_url({"db_type": "sqlite", "database": "../../etc/passwd"})
        check("build_url 拒绝穿越", False, "未抛异常")
    except ValueError:
        check("build_url 拒绝穿越", True)


# ---------- 4) current_user: cookie 优先于 X-User-Token 头 ----------
def test_current_user_cookie_preferred():
    auth.USER_SESSIONS.clear()
    tok_cookie = "cookie_tok_" + os.urandom(4).hex()
    tok_hdr = "hdr_tok_" + os.urandom(4).hex()
    auth.USER_SESSIONS[tok_cookie] = {"user": "alice", "role": "admin",
                                       "exp": 9e18, "last_active": 0}
    auth.USER_SESSIONS[tok_hdr] = {"user": "bob", "role": "write",
                                    "exp": 9e18, "last_active": 0}

    class _H:
        def __init__(self, headers):
            self.headers = headers

    # 仅 header(纯 API 客户端)
    h1 = _H({"X-User-Token": tok_hdr})
    check("仅 header -> bob", auth.current_user(h1)["user"] == "bob")
    # 仅 cookie(浏览器)
    h2 = _H({"Cookie": "dbm_user=" + tok_cookie})
    check("仅 cookie -> alice", auth.current_user(h2)["user"] == "alice")
    # 两者都有 -> cookie 优先(防 XSS 用 header 冒充, P0-4)
    h3 = _H({"Cookie": "dbm_user=" + tok_cookie, "X-User-Token": tok_hdr})
    check("cookie 优先于 header(P0-4)", auth.current_user(h3)["user"] == "alice",
          "被 header 冒充, 应返回 alice")


if __name__ == "__main__":
    test_is_safe_server()
    test_sqlite_sandbox()
    test_build_url_sandbox()
    test_current_user_cookie_preferred()
    print()
    if FAIL:
        print("P0 安全单测 FAIL: %d 项 -> %s" % (len(FAIL), FAIL))
        sys.exit(1)
    print("P0 安全单测全部通过 ✓")
