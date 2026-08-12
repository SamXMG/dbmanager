# -*- coding: utf-8 -*-
"""auth LDAP/注册开关单测: mock ldap3 模块, 不依赖真实 AD 服务器。
覆盖: 注册开关默认关/开、LDAP 未启用时本地登录回归、LDAP 认证成功(默认只读/按 users.json 配角色)、认证失败。
"""
import json
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import auth  # noqa: E402


# ---------- fake ldap3 ----------
class _LDAPInvalidCredentialsError(Exception):
    pass


class _FakeState:
    fail_bind = False       # 用户密码绑定是否失败
    entries_found = True    # 两步模式查询是否命中


class _FakeServer:
    def __init__(self, url, get_info=None):
        self.url = url


class _FakeConnection:
    def __init__(self, server, user=None, password=None, auto_bind=False,
                 receive_timeout=0):
        if auto_bind and _FakeState.fail_bind:
            raise _LDAPInvalidCredentialsError("invalid credentials")
        self.entries = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def search(self, base, flt, attributes=None):
        if _FakeState.entries_found:
            self.entries = [types.SimpleNamespace(
                distinguishedName="CN=%s,%s" % (flt.split("=")[1].split(",")[0], base))]
        else:
            self.entries = []


class TestRegisterSwitch(unittest.TestCase):
    """自助注册开关"""

    def _tmp_users(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "users.json")
        json.dump({"admin": {"pwd_hash": "x", "salt": "y", "role": "admin"}},
                  open(p, "w", encoding="utf-8"))
        return p

    def setUp(self):
        self._old_file = auth.USERS_FILE
        auth.USERS_FILE = self._tmp_users()
        self._old_reg = auth.register_enabled

    def tearDown(self):
        auth.USERS_FILE = self._old_file
        auth.register_enabled = self._old_reg

    def test_register_default_disabled(self):
        auth.register_enabled = lambda: False
        ok, msg = auth.register("newbie", "pass123")
        self.assertFalse(ok)
        self.assertIn("已关闭", msg)

    def test_register_enabled_via_flag(self):
        auth.register_enabled = lambda: True
        ok, msg = auth.register("newbie", "pass123")
        self.assertTrue(ok)
        users = auth._load_users()
        self.assertEqual(users["newbie"]["role"], "read")  # 自助注册默认只读


class TestLdapLogin(unittest.TestCase):
    """LDAP 认证登录"""

    def setUp(self):
        self._old_file = auth.USERS_FILE
        d = tempfile.mkdtemp()
        auth.USERS_FILE = os.path.join(d, "users.json")
        json.dump({"admin": {"pwd_hash": "x", "salt": "y", "role": "admin"}},
                  open(auth.USERS_FILE, "w", encoding="utf-8"))
        # 注入 fake ldap3
        self._old_ldap3 = sys.modules.get("ldap3")
        fake = types.ModuleType("ldap3")
        fake.Server = _FakeServer
        fake.Connection = _FakeConnection
        fake.ALL = "ALL"
        fake.core = types.SimpleNamespace(
            exceptions=types.SimpleNamespace(
                LDAPInvalidCredentialsError=_LDAPInvalidCredentialsError))
        sys.modules["ldap3"] = fake
        # 记录原 LDAP 配置
        self._old_url, self._old_base = auth.LDAP_URL, auth.LDAP_BASE
        self._old_bind = (auth.LDAP_BINDDN, auth.LDAP_BINDPW)
        _FakeState.fail_bind = False
        _FakeState.entries_found = True

    def tearDown(self):
        auth.USERS_FILE = self._old_file
        auth.LDAP_URL, auth.LDAP_BASE = self._old_url, self._old_base
        auth.LDAP_BINDDN, auth.LDAP_BINDPW = self._old_bind
        if self._old_ldap3 is None:
            sys.modules.pop("ldap3", None)
        else:
            sys.modules["ldap3"] = self._old_ldap3

    def test_ldap_disabled_local_login(self):
        auth.LDAP_URL, auth.LDAP_BASE = "", ""
        # 测试文件 admin 用真实 pbkdf2 哈希(便于测本地登录)
        salt = "a" * 32
        users = auth._load_users()
        users["admin"] = {"pwd_hash": auth._hash("admin123", salt),
                          "salt": salt, "role": "admin"}
        json.dump(users, open(auth.USERS_FILE, "w", encoding="utf-8"))
        st, payload = auth.login("admin", "admin123")
        self.assertEqual(st, "ok")
        self.assertEqual(payload[2], "admin")
        st, _ = auth.login("admin", "wrong")
        self.assertEqual(st, "fail")  # 本地密码错不降级 LDAP(本地账号优先)

    def test_ldap_login_success_default_read(self):
        auth.LDAP_URL, auth.LDAP_BASE = "ldap://fake:389", "dc=test,dc=com"
        st, payload = auth.login("zhangsan", "adpass123")
        self.assertEqual(st, "ok")
        tok, role, user = payload
        self.assertEqual(user, "zhangsan")
        self.assertEqual(role, "read")  # 未在 users.json 配置 -> 默认只读

    def test_ldap_login_role_from_users(self):
        # 管理员预先在 users.json 给 LDAP 用户配 write 角色(无密码字段)
        users = auth._load_users()
        users["lisi"] = {"role": "write"}
        json.dump(users, open(auth.USERS_FILE, "w", encoding="utf-8"))
        auth.LDAP_URL, auth.LDAP_BASE = "ldap://fake:389", "dc=test,dc=com"
        st, payload = auth.login("lisi", "adpass123")
        self.assertEqual(st, "ok")
        self.assertEqual(payload[1], "write")

    def test_ldap_bind_fail(self):
        auth.LDAP_URL, auth.LDAP_BASE = "ldap://fake:389", "dc=test,dc=com"
        _FakeState.fail_bind = True
        st, _ = auth.login("zhangsan", "wrong")
        self.assertEqual(st, "fail")

    def test_ldap_two_step_binddn(self):
        auth.LDAP_URL, auth.LDAP_BASE = "ldap://fake:389", "dc=test,dc=com"
        auth.LDAP_BINDDN, auth.LDAP_BINDPW = "cn=admin,dc=test,dc=com", "adminpw"
        st, payload = auth.login("wangwu", "adpass123")
        self.assertEqual(st, "ok")
        self.assertEqual(payload[0] and True, True)  # 两步绑定路径可用

    def test_ldap_no_entries_fallback_fail(self):
        auth.LDAP_URL, auth.LDAP_BASE = "ldap://fake:389", "dc=test,dc=com"
        auth.LDAP_BINDDN, auth.LDAP_BINDPW = "cn=admin,dc=test,dc=com", "adminpw"
        _FakeState.entries_found = False
        st, _ = auth.login("ghost", "adpass123")
        self.assertEqual(st, "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
