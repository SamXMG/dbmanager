# -*- coding: utf-8 -*-
"""P0-3 端到端验证: 起真实服务 → 登录(admin, write) →
  · 手动连接携带云元数据地址(169.254.169.254)必须被 SSRF 防护拒绝(400)
  · 手动连接 SQLite 携带 ../../ 穿越路径必须被沙箱拒绝(400)
  · 合法 SQLite 相对路径(落在数据根内)仍可用(200, 控制用例)
纯 SQLite, 无外部依赖。用法: python tests/e2e_p0_ssrf.py [port]
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18778
BASE = "http://127.0.0.1:%d" % PORT
WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKDIR)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(path, method="GET", body=None, headers=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def J(b):
    return json.loads(b or b"{}")


def main():
    from db import sqlitedb
    _users_bak = sqlitedb.users_load()

    port = _free_port() if PORT == 0 else PORT
    _prog_db = os.path.join(tempfile.gettempdir(),
                            "dbm_p0_ssrf_%d_%d.db" % (port, int(time.time())))
    env = dict(os.environ, DBM_PORT=str(port), DBM_NO_OPEN="1", DBM_DB_FILE=_prog_db,
               DBM_DEFAULT_PWD="P0Ssrf@2026")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(WORKDIR, "app.py")],
        cwd=WORKDIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("服务启动超时")

        ok = fail = 0

        def check(n, cond, extra=""):
            nonlocal ok, fail
            if cond:
                ok += 1
                print("  ✓", n)
            else:
                fail += 1
                print("  ✗", n, extra)

        # 登录 admin(默认账号, write 角色)
        s, b = req("/api/login", "POST", {"username": "admin", "password": "P0Ssrf@2026"})
        check("admin 登录", s == 200 and J(b).get("role") == "admin", (s, b[:80]))
        h = {}
        if s == 200:
            h["X-User-Token"] = J(b)["token"]
            if J(b).get("must_change_pwd"):
                req("/api/password", "POST",
                    {"old_password": "P0Ssrf@2026", "new_password": "P0SsrfNew@2026"}, h)

        # 1) SSRF: 云元数据地址必须拒绝
        s, b = req("/api/connect", "POST",
                   {"db_type": "mysql", "server": "169.254.169.254", "port": 3306,
                    "database": "x"}, h)
        check("SSRF 防护: 拒绝云元数据地址(400)", s == 400, (s, b[:120]))

        # 2) SQLite 路径穿越必须拒绝
        s, b = req("/api/connect", "POST",
                   {"db_type": "sqlite", "database": "../../../../etc/passwd"}, h)
        check("路径沙箱: 拒绝 ../../ 穿越(400)", s == 400, (s, b[:120]))

        # 3) 控制用例: 合法 SQLite 相对路径(落在数据根内)仍可用
        s, b = req("/api/connect", "POST",
                   {"db_type": "sqlite", "database": "p0_ci_ok.db"}, h)
        check("控制用例: 合法 SQLite 连接成功(200)", s == 200 and J(b).get("session"), (s, b[:120]))

        req("/api/shutdown", "POST", {})
        print("\nP0-3 SSRF/沙箱 E2E: %d 通过, %d 失败" % (ok, fail))
        return 1 if fail else 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            # 控制用例的相对路径按 cwd(=WORKDIR)解析, 落在该处
            for cand in (os.path.join(WORKDIR, "p0_ci_ok.db"),
                         os.path.join(WORKDIR, "data", "p0_ci_ok.db")):
                if os.path.exists(cand):
                    os.remove(cand)
        except Exception:
            pass
        if _users_bak is not None:
            try:
                sqlitedb.users_save(_users_bak)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
