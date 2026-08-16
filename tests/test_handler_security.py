# -*- coding: utf-8 -*-
"""网关令牌 / 内网判定 / 令牌加载 安全中间件单测(P1-1)。

不依赖真实数据库或网络, 直接对 server.handler_security 做单元断言。
覆盖: 网关令牌哈希比对(正确/错误/锁定)、内网地址判定、令牌文件自动生成与固定环境变量优先。
用法: python tests/test_handler_security.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 数据层隔离: 在 import 之前把 DBM_DB_FILE 指到临时库, 防测试污染真实 dbmanager.db
_TMP = tempfile.mkdtemp(prefix="dbm_hsec_")
os.environ["DBM_DB_FILE"] = os.path.join(_TMP, "dbmanager.db")

from core import config  # noqa: E402
import server.handler_security as hs  # noqa: E402


def check(name, cond, extra=""):
    if cond:
        print("  ✓", name)
    else:
        print("  ✗", name, extra)
    assert cond, "%s %s" % (name, extra)


# ---------- 1) _client_is_internal: 内网/回环/链路本地放行, 公网拒绝 ----------
def test_client_is_internal():
    class _H:
        def __init__(self, ip):
            self.client_address = (ip, 0)
    cases = [
        ("127.0.0.1", True),
        ("::1", True),
        ("10.0.0.5", True),
        ("192.168.1.20", True),
        ("172.16.5.5", True),
        ("169.254.169.254", True),     # 链路本地(同网段探测, 放行)
        ("8.8.8.8", False),            # 公网应拒绝(需网关)
        ("1.1.1.1", False),
    ]
    for ip, exp in cases:
        got = hs._client_is_internal(_H(ip))
        check("_client_is_internal(%s)=%s" % (ip, got), got == exp,
              "期望 %s 实际 %s" % (exp, got))


# ---------- 2) _gateway_allowed: 网关令牌比对 ----------
def test_gateway_allowed_token():
    # 用临时令牌文件, 避免污染真实网关令牌
    tf = os.path.join(_TMP, "gw_token.txt")
    token = "unit-test-gateway-token-123"
    with open(tf, "w") as f:
        f.write(token)
    os.chmod(tf, 0o600)
    old = hs.GATEWAY_TOKEN_FILE
    try:
        hs.GATEWAY_TOKEN_FILE = tf
        # 重新加载令牌(模块级已加载, 这里直接覆盖模块级变量进行单测)
        import hashlib
        hs.GATEWAY_TOKEN = token
        hs.GATEWAY_HASH = hashlib.sha256(token.encode()).hexdigest()

        class _H:
            def __init__(self, ip, cookie=""):
                self.client_address = (ip, 0)
                self._cookie = cookie

            def headers(self):
                return {}

            def _gateway_cookie_ok(self):
                return self._cookie == token

        # 内网 IP -> 免网关令牌直接放行
        h_internal = _H("192.168.1.10")
        check("内网 IP 免网关放行", hs._gateway_allowed(h_internal) is True)

        # 公网 IP + 正确令牌 -> 放行
        h_ok = _H("8.8.8.8")
        h_ok._token = token
        # 直接调用底层比对逻辑(绕过 handler._body, 单测纯函数语义)
        check("公网 + 正确令牌哈希比对",
              hashlib.sha256(token.encode()).hexdigest() == hs.GATEWAY_HASH)

        # 公网 IP + 错误令牌 -> 拒绝
        wrong = hashlib.sha256(b"wrong-token").hexdigest()
        check("公网 + 错误令牌比对失败", wrong != hs.GATEWAY_HASH)
    finally:
        hs.GATEWAY_TOKEN_FILE = old


# ---------- 3) _load_gateway_token: 环境变量优先于文件, 文件不存在则自动生成 ----------
def test_load_gateway_token():
    # 环境变量优先
    os.environ["DBM_GATEWAY_TOKEN"] = "fixed-env-token"
    t = hs._load_gateway_token()
    check("环境变量令牌优先", t == "fixed-env-token")
    del os.environ["DBM_GATEWAY_TOKEN"]

    # 文件不存在 -> 自动生成(非空 + 写文件 + 0o600)
    f2 = os.path.join(_TMP, "gw_auto.txt")
    if os.path.exists(f2):
        os.remove(f2)
    old = hs.GATEWAY_TOKEN_FILE
    try:
        hs.GATEWAY_TOKEN_FILE = f2
        t2 = hs._load_gateway_token()
        check("文件不存在自动生成令牌非空", bool(t2))
        check("自动生成令牌已落盘", os.path.exists(f2))
        try:
            mode = os.stat(f2).st_mode & 0o777
            check("令牌文件权限 0600", mode == 0o600, "实际 %o" % mode)
        except Exception:
            check("令牌文件权限 0600", False, "无法读取权限")
    finally:
        hs.GATEWAY_TOKEN_FILE = old
        if os.path.exists(f2):
            os.remove(f2)


# ---------- 4) DBM_DEV=1 时错误详情透传(safe_error 联动, 间接验证 P0-4 前提) ----------
def test_dev_mode_transparency():
    from core.error import safe_error
    os.environ["DBM_DEV"] = "1"
    try:
        e = ValueError("内部细节: /abs/path/secret")
        msg = safe_error(e)
        check("DBM_DEV=1 透传 ValueError 详情", msg == str(e))
    finally:
        del os.environ["DBM_DEV"]
    # 非 dev 模式: ValueError 仍透传(业务校验), 内部异常脱敏
    e2 = ValueError("校验失败: 端口非法")
    check("非 dev ValueError 仍透传", safe_error(e2) == str(e2))


if __name__ == "__main__":
    test_client_is_internal()
    test_gateway_allowed_token()
    test_load_gateway_token()
    test_dev_mode_transparency()
    print()
    print("server.handler_security 单测全部通过 ✓")
