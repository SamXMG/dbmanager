# -*- coding: utf-8 -*-
"""内网 ACL 端到端: 连接可见性(visible_to) + 生产库强制只读(mode=read_only) + admin 角色
运行前提: 服务已启动(正常模式, users.json 存在)。用后自动清理测试账号/连接/库文件。
"""
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8770"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import sqlitedb
USERS = os.path.join(ROOT, "users.json")   # 遗留路径(迁移前兼容), 数据实际在 SQLite

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("PASS", name)
    else:
        failed += 1
        print("FAIL", name, extra)


def req(m, p, o=None, t=None):
    h = {"Content-Type": "application/json"}
    if t:
        h["X-User-Token"] = t
    r = urllib.request.Request(BASE + p, data=json.dumps(o).encode() if o else None,
                               headers=h, method=m)
    try:
        resp = urllib.request.urlopen(r)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def mk_user(name, pwd, role):
    salt = secrets.token_hex(16)
    return {name: {"pwd_hash": hashlib.pbkdf2_hmac(
        "sha256", pwd.encode(), bytes.fromhex(salt), 120000).hex(),
        "salt": salt, "role": role}}


def main():
    # ---- 准备: 临时账号 + 3 个 sqlite 库 ----
    users = sqlitedb.users_load()
    saved = dict(users)
    users.update(mk_user("alice", "alice123", "write"))
    users.update(mk_user("bob", "bob12345", "read"))
    sqlitedb.users_save(users)

    dbs = {}
    for n in ("_aclA.db", "_aclB.db", "_aclC.db"):
        p = os.path.join(ROOT, n)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass  # 沙箱回收站不可用等, 用 IF NOT EXISTS 幂等建表
        c = sqlite3.connect(p)
        c.execute("CREATE TABLE IF NOT EXISTS t1 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
        c.execute("DELETE FROM t1")
        c.execute("INSERT INTO t1 (name) VALUES ('x')")
        c.commit()
        c.close()
        dbs[n] = n   # connect 传相对路径(服务 cwd=项目根, 规避中文目录绝对路径连接失败)

    try:
        # ---- admin 登录 ----
        # 密码适配: CI/本地 e2e 可能设 DBM_DEFAULT_PWD 覆盖首次建库口令(强制改密 P0-1 要求非默认口令)
        adm_pwd = os.environ.get("DBM_DEFAULT_PWD") or "admin123"
        st, d = req("POST", "/api/login", {"username": "admin", "password": adm_pwd})
        adm_tok = d.get("token", "")
        check("admin 登录", st == 200)
        if d.get("must_change_pwd"):
            # 首次部署默认账号需先改密(否则建连接 403); 脚本适配产品行为
            st2, _ = req("POST", "/api/password", {"old_password": adm_pwd, "new_password": "E2eAdmin@2026"}, adm_tok)
            check("admin 首次改密", st2 == 200)

        # admin 建连接: A(仅 alice 可见) / B(公开) / C(read_only, 仅 alice 可见)
        st, d = req("POST", "/api/connections", {"name": "ACL-A", "db_type": "sqlite",
                     "database": dbs["_aclA.db"], "visible_to": ["alice"]}, adm_tok)
        check("admin 建私有连接 A", st == 200)
        st, d = req("POST", "/api/connections", {"name": "ACL-B", "db_type": "sqlite",
                     "database": dbs["_aclB.db"]}, adm_tok)
        check("admin 建公开连接 B", st == 200)
        st, d = req("POST", "/api/connections", {"name": "ACL-C", "db_type": "sqlite",
                     "database": dbs["_aclC.db"], "visible_to": ["alice"],
                     "mode": "read_only"}, adm_tok)
        check("admin 建只读连接 C", st == 200 and d.get("connection", {}).get("mode") == "read_only")

        # ---- alice(write) 登录: 应看到 A/B/C ----
        st, d = req("POST", "/api/login", {"username": "alice", "password": "alice123"})
        ali_tok = d.get("token", "")
        check("alice 登录", st == 200 and d.get("role") == "write")
        st, d = req("GET", "/api/connections", t=ali_tok)
        names = set(c["name"] for c in d)
        check("alice 可见 A/B/C", st == 200 and {"ACL-A", "ACL-B", "ACL-C"} <= names,
              sorted(names))

        # ---- bob(read) 登录: 只应看到公开连接(旧连接无 visible_to + ACL-B), 看不到 A/C ----
        st, d = req("POST", "/api/login", {"username": "bob", "password": "bob12345"})
        bob_tok = d.get("token", "")
        check("bob 登录", st == 200 and d.get("role") == "read")
        st, d = req("GET", "/api/connections", t=bob_tok)
        names = set(c["name"] for c in d)
        check("bob 见 B 不见 A/C",
              st == 200 and "ACL-B" in names and "ACL-A" not in names and "ACL-C" not in names,
              sorted(names))

        # ---- 非 admin 设置 visible_to -> 403 ----
        st, d = req("POST", "/api/connections", {"name": "ACL-A", "db_type": "sqlite",
                     "database": dbs["_aclA.db"], "visible_to": ["bob"]}, ali_tok)
        check("alice 改可见性 -> 403", st == 403)

        # ---- read_only 连接 C: alice(write) 写操作被拒 ----
        st, d = req("POST", "/api/connect", {"name": "ACL-C"}, ali_tok)
        ss_c = d.get("session", "")
        check("alice 连接 C(只读)", st == 200)
        st, d = req("POST", "/api/row", {"s": "main", "t": "t1", "transaction": False,
                     "values": {"name": "hack"}}, t=ali_tok, )
        st, d = req("POST", "/api/row", {"s": "main", "t": "t1", "transaction": False,
                     "values": {"name": "hack"}}, t=ali_tok) if False else (st, d)
        # 需带 C 会话头重发
        h = {"Content-Type": "application/json", "X-User-Token": ali_tok, "X-Session": ss_c}
        r = urllib.request.Request(BASE + "/api/row", data=json.dumps(
            {"s": "main", "t": "t1", "transaction": False, "values": {"name": "hack"}}).encode(),
            headers=h, method="POST")
        try:
            resp = urllib.request.urlopen(r)
            st2, d2 = resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            st2 = e.code
            try:
                d2 = json.loads(e.read().decode())
            except Exception:
                d2 = {}
        check("read_only 连接写行 -> 403", st2 == 403, str(st2))
        # 只读 SELECT 放行
        r = urllib.request.Request(BASE + "/api/data?s=main&t=t1&page=1&size=10&where=&order=",
                                   headers={"X-Session": ss_c, "X-User-Token": ali_tok})
        resp = urllib.request.urlopen(r)
        d3 = json.loads(resp.read().decode())
        check("read_only 连接读数据 200", resp.status == 200 and d3.get("total") == 1)
        # SQL 写模式也被拒
        r = urllib.request.Request(BASE + "/api/sql", data=json.dumps(
            {"sql": "INSERT INTO t1 (name) VALUES ('y')", "write": True}).encode(),
            headers=h, method="POST")
        try:
            resp = urllib.request.urlopen(r)
            st3 = resp.status
        except urllib.error.HTTPError as e:
            st3 = e.code
        check("read_only 连接 SQL 写 -> 403", st3 == 403, str(st3))

        # ---- 非只读连接 B: alice 可正常写 ----
        st, d = req("POST", "/api/connect", {"name": "ACL-B"}, ali_tok)
        ss_b = d.get("session", "")
        hb = {"Content-Type": "application/json", "X-User-Token": ali_tok, "X-Session": ss_b}
        r = urllib.request.Request(BASE + "/api/row", data=json.dumps(
            {"s": "main", "t": "t1", "transaction": False, "values": {"name": "ok"}}).encode(),
            headers=hb, method="POST")
        try:
            resp = urllib.request.urlopen(r)
            st4 = resp.status
        except urllib.error.HTTPError as e:
            st4 = e.code
        check("普通连接写行 -> 200", st4 == 200, str(st4))

        # ---- 连接列表带 ACL 元数据(前端标记用) ----
        st, d = req("GET", "/api/connections", t=adm_tok)
        c = next((x for x in d if x["name"] == "ACL-C"), {})
        check("列表含 visible_to/mode 元数据",
              c.get("visible_to") == ["alice"] and c.get("mode") == "read_only", str(c))

        # ---- admin 角色: 账号管理仍可用 ----
        st, d = req("GET", "/api/users", t=adm_tok)
        check("admin 访问账号管理 200", st == 200)
    finally:
        # ---- 清理 ----
        for t in (adm_tok, ali_tok, bob_tok):
            if t:
                req("POST", "/api/connections/delete", {"name": "ACL-A"}, t)
                req("POST", "/api/connections/delete", {"name": "ACL-B"}, t)
                req("POST", "/api/connections/delete", {"name": "ACL-C"}, t)
        # 恢复初始快照(改密/建连接前的用户数据状态), 避免污染后续 e2e
        users = dict(saved)
        sqlitedb.users_save(users)
        for p in dbs.values():
            try:
                os.remove(p)
            except Exception:
                pass

    print("== %d passed, %d failed ==" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
