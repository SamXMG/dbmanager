# -*- coding: utf-8 -*-
"""HTTP 冒烟: 起真实服务 → 登录(如启用) → 连接 → 数据/SQL/导出/备份 → 关机。
纯 SQLite, 无外部数据库依赖, CI 与本地通用。
用法: python tests/e2e_http_smoke.py [port]
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18777
BASE = "http://127.0.0.1:%d" % PORT
WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _set_base(port):
    global BASE
    BASE = "http://127.0.0.1:%d" % port


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
    # 1) 准备测试库(唯一后缀 + 相对路径: 绝对路径含中文目录在部分环境连接异常)
    import uuid
    db = os.path.basename(os.path.join(WORKDIR, "_ci_smoke_%s.db" % uuid.uuid4().hex[:6]))
    db_abs = os.path.join(WORKDIR, db)
    import sqlite3
    c = sqlite3.connect(db_abs)
    c.executescript("CREATE TABLE emp (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);"
                    "INSERT INTO emp (name, age) VALUES ('张三', 30), ('李四', 25);")
    c.commit()
    c.close()

    # 2) 起服务
    port = _free_port() if PORT == 0 else PORT
    _set_base(port)
    env = dict(os.environ, DBM_PORT=str(port), DBM_NO_OPEN="1")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(WORKDIR, "app.py")],
        cwd=WORKDIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base2 = "http://127.0.0.1:%d" % port
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(base2 + "/", timeout=2)
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

        # 3) 鉴权守卫: auth 开启时未登录访问敏感接口必须 401(回归保护 P0-D1)
        s, b = req("/api/config")
        auth_req = bool(J(b).get("auth_required")) if s == 200 else False
        if auth_req:
            s, b = req("/api/backup")
            check("未登录 backup 401(auth 开启)", s == 401 and b"require_login" in b, (s, b[:80]))
            s, b = req("/api/connect", "POST", {"db_type": "sqlite", "database": db})
            check("未登录 connect 401(auth 开启)", s == 401)
        else:
            print("  · auth 未启用, 跳过未登录断言(CI 默认场景)")

        # 4) 连接(兼容 auth 启用/关闭)
        s, b = req("/api/connect", "POST", {"db_type": "sqlite", "database": db})
        h = {}
        if s == 401:  # auth 启用: 先登录默认账号
            s2, b2 = req("/api/login", "POST", {"username": "admin", "password": "admin123"})
            if s2 == 200:
                h["X-User-Token"] = J(b2)["token"]
                if J(b2).get("must_change_pwd"):
                    # 首次部署默认账号需先改密(否则 connect 403); 脚本适配产品行为
                    req("/api/password", "POST", {"old_password": "admin123", "new_password": "E2eAdmin@2026"}, h)
                s, b = req("/api/connect", "POST", {"db_type": "sqlite", "database": db}, h)
        check("connect", s == 200 and J(b).get("session"), b[:120])
        h["X-Session"] = J(b)["session"]

        s, b = req("/api/tables", headers=h)
        check("tables", isinstance(J(b), list) and any(t["name"] == "emp" for t in J(b)))
        s, b = req("/api/data?s=&t=emp&page=1&size=10", headers=h)
        check("data", s == 200 and J(b).get("total") == 2)
        s, b = req("/api/sql", "POST", {"sql": "SELECT COUNT(*) AS c FROM emp"}, h)
        check("sql", s == 200 and J(b).get("ok") and J(b)["results"][0]["rows"][0]["c"] == 2)
        s, b = req("/api/export?s=&t=emp&fmt=csv", headers=h)
        check("export csv", s == 200 and b"name" in b)
        s, b = req("/api/backup", headers=h)
        check("backup", s == 200 and b"CREATE TABLE" in b)
        s, b = req("/api/explain", "POST", {"sql": "SELECT * FROM emp WHERE id > 1"}, h)
        check("explain", s == 200 and J(b).get("rows"))
        s, b = req("/api/row", "POST", {"s": "", "t": "emp", "values": {"name": "CI", "age": 1}}, h)
        check("row insert", s == 200 and J(b).get("ok"))
        s, b = req("/api/data?s=&t=emp&page=1&size=10", headers=h)
        check("insert 生效", J(b).get("total") == 3)

        req("/api/shutdown", "POST", {})
        print("\nHTTP 冒烟: %d 通过, %d 失败" % (ok, fail))
        return 1 if fail else 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            if os.path.exists(db_abs):
                os.remove(db_abs)
        except Exception:
            pass  # 某些沙箱环境拦截删除, CI 无此限制


if __name__ == "__main__":
    sys.exit(main())
