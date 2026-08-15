# -*- coding: utf-8 -*-
"""dbmanager - 程序自身数据的 SQLite 存储(用户/权限/连接配置) v2
取代散落的 users.json / connections.json / tasks.json 文件:
- users:       规范化表(真列): username/role/status/is_default/pwd_hash/salt/created_at
- user_perms:  权限关系表: username + conn_name + can_read + can_write(连接级读写开关)
- user_perm_tables: 表级权限关系表: username + conn_name + table_name + is_deny(白名单/黑名单)
- connections: 连接配置(第 2 步将拆真列; 当前 data JSON 列)
- meta:        schema 版本
- WAL 模式 + 每操作短连接(低频访问, 避免跨线程复用连接; busy_timeout 防写锁竞争)
- 自动迁移: ①旧 users.json 文件 -> SQLite; ②旧 users 表(data JSON 列) -> 规范化表 v2
  源 JSON 文件改名 .bak(保留现场)
"""
import json
import os
import sqlite3
import threading
import time

from core import config  # 模块引用: config.BASE_DIR 可能在运行时被测试/部署改写, 需动态取值

# 数据库文件: 默认项目根 dbmanager.db; DBM_DB_FILE(或 dbmanager.conf [server] db_file) 可自定义位置。
# 动态求值(而非模块级常量): 兼容 config.BASE_DIR 在运行时被测试/部署改写
def db_file():
    return config.conf("DBM_DB_FILE") or os.path.join(config.BASE_DIR, "dbmanager.db")


SCHEMA_VERSION = "4"

# 初始化仅执行一次(进程内): 避免每个请求触发建表写事务(多线程高并发下写锁竞争/假死)
_INIT_DONE = False
_INIT_LOCK = threading.Lock()


def _connect():
    """短连接 + WAL + busy_timeout(写锁等待 10s, 防并发写 SQLITE_BUSY)"""
    c = sqlite3.connect(db_file(), timeout=10)
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=10000")
        c.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    return c


def _tx(fn):
    """事务包裹: 开连接 -> fn(conn) -> commit -> close; 异常 rollback 并上抛"""
    conn = _connect()
    try:
        r = fn(conn)
        conn.commit()
        return r
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _users_v2_ddl(table):
    """users 规范化表 v2 的 DDL(建表/迁移临时表共用)"""
    return (
        "CREATE TABLE IF NOT EXISTS %s ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "username TEXT UNIQUE NOT NULL,"
        "role TEXT NOT NULL DEFAULT 'read',"
        "status TEXT NOT NULL DEFAULT 'active',"
        "is_default INTEGER NOT NULL DEFAULT 0,"
        "pwd_hash TEXT,"
        "salt TEXT,"
        "created_at TEXT DEFAULT '')" % table)


def _migrate_users_table(conn):
    """旧 users 表(data JSON 列) -> 规范化表 v2(拆列 + 权限关系表)。
    幂等: 已规范化则跳过。迁移在事务内完成, 失败回滚保留旧表。"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "username" in cols:
        return  # 已是 v2
    conn.execute("DROP TABLE IF EXISTS users_new")
    conn.execute(_users_v2_ddl("users_new"))
    conn.execute("CREATE TABLE IF NOT EXISTS user_perms ("
                 "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 "username TEXT NOT NULL, conn_name TEXT NOT NULL,"
                 "can_read INTEGER NOT NULL DEFAULT 0, can_write INTEGER NOT NULL DEFAULT 0,"
                 "UNIQUE(username, conn_name))")
    conn.execute("CREATE TABLE IF NOT EXISTS user_perm_tables ("
                 "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 "username TEXT NOT NULL, conn_name TEXT NOT NULL, table_name TEXT NOT NULL,"
                 "is_deny INTEGER NOT NULL DEFAULT 0,"
                 "UNIQUE(username, conn_name, table_name))")
    for name, data_json in conn.execute("SELECT name, data FROM users"):
        try:
            u = json.loads(data_json)
        except Exception:
            continue
        conn.execute(
            "INSERT INTO users_new(username, role, status, is_default, pwd_hash, salt, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (name, u.get("role", "read"), u.get("status", "active"),
             1 if u.get("is_default") else 0,
             u.get("pwd_hash"), u.get("salt"), u.get("created_at", "")))
        for cn, p in (u.get("perms") or {}).items():
            conn.execute(
                "INSERT INTO user_perms(username, conn_name, can_read, can_write) VALUES(?,?,?,?)",
                (name, cn, 1 if p.get("read") else 0, 1 if p.get("write") else 0))
            for t in (p.get("tables") or []):
                conn.execute(
                    "INSERT INTO user_perm_tables(username, conn_name, table_name, is_deny)"
                    " VALUES(?,?,?,0)", (name, cn, t))
            for t in (p.get("deny_tables") or []):
                conn.execute(
                    "INSERT INTO user_perm_tables(username, conn_name, table_name, is_deny)"
                    " VALUES(?,?,?,1)", (name, cn, t))
    conn.execute("DROP TABLE users")
    conn.execute("ALTER TABLE users_new RENAME TO users")


def init_db():
    """建表(幂等): 进程内仅执行一次; 旧表结构自动迁移到当前版本"""
    global _INIT_DONE
    if _INIT_DONE:
        return
    with _INIT_LOCK:
        if _INIT_DONE:
            return
        def _init(conn):
            conn.execute(_users_v2_ddl("users"))
            conn.execute("CREATE TABLE IF NOT EXISTS user_perms ("
                         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "username TEXT NOT NULL, conn_name TEXT NOT NULL,"
                         "can_read INTEGER NOT NULL DEFAULT 0, can_write INTEGER NOT NULL DEFAULT 0,"
                         "UNIQUE(username, conn_name))")
            conn.execute("CREATE TABLE IF NOT EXISTS user_perm_tables ("
                         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "username TEXT NOT NULL, conn_name TEXT NOT NULL, table_name TEXT NOT NULL,"
                         "is_deny INTEGER NOT NULL DEFAULT 0,"
                         "UNIQUE(username, conn_name, table_name))")
            conn.execute(_conns_v3_ddl("connections"))
            conn.execute("CREATE TABLE IF NOT EXISTS audit_log ("
                         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "ts TEXT NOT NULL,"
                         "ip TEXT NOT NULL DEFAULT '',"
                         "action TEXT NOT NULL DEFAULT '',"
                         "detail TEXT NOT NULL DEFAULT '',"
                         "username TEXT NOT NULL DEFAULT '')")
            conn.execute("CREATE TABLE IF NOT EXISTS tasks ("
                         "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "name TEXT NOT NULL DEFAULT '',"
                         "action TEXT NOT NULL DEFAULT 'backup',"
                         "conn_name TEXT NOT NULL DEFAULT '',"
                         "interval_min INTEGER NOT NULL DEFAULT 60,"
                         "enabled INTEGER NOT NULL DEFAULT 1,"
                         "last_run REAL,"
                         "next_run REAL,"
                         "last_result TEXT NOT NULL DEFAULT '',"
                         "created_at REAL)")
            conn.execute("CREATE TABLE IF NOT EXISTS meta ("
                         "key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            # 旧表结构迁移到当前版本(幂等: 已规范化则跳过)
            _migrate_users_table(conn)
            _migrate_conns_table(conn)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
                         (SCHEMA_VERSION,))
        try:
            _tx(_init)
        except Exception:
            pass  # 首次建表失败不致命(后续读写会再尝试); 保持旧行为
        _INIT_DONE = True


# ----------------------------- 用户(规范化表 + 权限关系表) -----------------------------

def users_load():
    """全量用户 -> {username: {pwd_hash, salt, role, status, is_default?, perms}}。
    从规范化表 + 权限关系表组装(与 auth 业务层契约保持一致)"""
    init_db()
    def _load(conn):
        users = {}
        for uname, role, status, is_default, ph, salt, created_at in conn.execute(
                "SELECT username, role, status, is_default, pwd_hash, salt, created_at FROM users"):
            rec = {"pwd_hash": ph, "salt": salt, "role": role, "status": status}
            if is_default:
                rec["is_default"] = True
            if created_at:
                rec["created_at"] = created_at
            users[uname] = rec
        # 连接级权限
        perms = {}
        for uname, cn, cr, cw in conn.execute(
                "SELECT username, conn_name, can_read, can_write FROM user_perms"):
            perms.setdefault(uname, {})[cn] = {"read": bool(cr), "write": bool(cw),
                                               "tables": [], "deny_tables": []}
        # 表级权限(白名单 is_deny=0 / 黑名单 is_deny=1)
        for uname, cn, tname, is_deny in conn.execute(
                "SELECT username, conn_name, table_name, is_deny FROM user_perm_tables"):
            p = perms.setdefault(uname, {}).setdefault(
                cn, {"read": False, "write": False, "tables": [], "deny_tables": []})
            (p["deny_tables"] if is_deny else p["tables"]).append(tname)
        for uname, pm in perms.items():
            users.setdefault(uname, {})["perms"] = pm
        return users
    try:
        return _tx(_load)
    except Exception:
        return {}


def users_save(users):
    """全量覆盖写入(与旧 _save 语义一致): 拆解 dict 写入规范化表 + 权限关系表"""
    init_db()
    def _save(conn):
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM user_perms")
        conn.execute("DELETE FROM user_perm_tables")
        for uname, u in users.items():
            conn.execute(
                "INSERT INTO users(username, role, status, is_default, pwd_hash, salt, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (uname, u.get("role", "read"), u.get("status", "active"),
                 1 if u.get("is_default") else 0,
                 u.get("pwd_hash"), u.get("salt"), u.get("created_at", "")))
            for cn, p in (u.get("perms") or {}).items():
                conn.execute(
                    "INSERT INTO user_perms(username, conn_name, can_read, can_write) VALUES(?,?,?,?)",
                    (uname, cn, 1 if p.get("read") else 0, 1 if p.get("write") else 0))
                for t in (p.get("tables") or []):
                    conn.execute(
                        "INSERT INTO user_perm_tables(username, conn_name, table_name, is_deny)"
                        " VALUES(?,?,?,0)", (uname, cn, t))
                for t in (p.get("deny_tables") or []):
                    conn.execute(
                        "INSERT INTO user_perm_tables(username, conn_name, table_name, is_deny)"
                        " VALUES(?,?,?,1)", (uname, cn, t))
    _tx(_save)


def has_users():
    """是否存在用户记录(取代 os.path.exists(users.json) 的启用判断)"""
    init_db()
    def _q(conn):
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return bool(row and row[0] > 0)
    try:
        return _tx(_q)
    except Exception:
        return False


def migrate_users_json(json_path):
    """旧 users.json -> SQLite(仅当 SQLite 无用户且 json 存在); 成功后 json 改名 .bak"""
    init_db()
    if not os.path.exists(json_path):
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not data:
            return False
        if has_users():
            return False
        users_save(data)
        os.replace(json_path, json_path + ".bak")
        return True
    except Exception:
        return False


# ----------------------------- 连接配置(规范化真列) -----------------------------

def _conns_v3_ddl(table):
    """connections 规范化表 v3: 主字段拆真列; visible_to/tunnel 属列表/嵌套配置保留 JSON 列"""
    return (
        "CREATE TABLE IF NOT EXISTS %s ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "name TEXT UNIQUE NOT NULL,"
        "db_type TEXT NOT NULL DEFAULT '',"
        "server TEXT NOT NULL DEFAULT '',"
        "port TEXT NOT NULL DEFAULT '',"
        "database TEXT NOT NULL DEFAULT '',"
        "uid TEXT NOT NULL DEFAULT '',"
        "pwd_enc TEXT NOT NULL DEFAULT '',"
        "mode TEXT NOT NULL DEFAULT '',"
        "visible_to TEXT NOT NULL DEFAULT '[]',"
        "tunnel TEXT NOT NULL DEFAULT '{}')" % table)


def _migrate_conns_table(conn):
    """旧 connections 表(data JSON 列) -> 规范化表 v3(拆列)。
    幂等: 已规范化则跳过; 事务内完成失败回滚保留旧表。"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(connections)").fetchall()]
    if "db_type" in cols and "server" in cols:
        return  # 已是 v3
    conn.execute("DROP TABLE IF EXISTS connections_new")
    conn.execute(_conns_v3_ddl("connections_new"))
    for name, data_json in conn.execute("SELECT name, data FROM connections"):
        try:
            c = json.loads(data_json)
        except Exception:
            continue
        conn.execute(
            "INSERT INTO connections_new(name, db_type, server, port, database, uid,"
            " pwd_enc, mode, visible_to, tunnel) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (name, c.get("db_type", ""), c.get("server", ""), c.get("port", ""),
             c.get("database", ""), c.get("uid", ""), c.get("pwd_enc", ""),
             c.get("mode", ""),
             json.dumps(c.get("visible_to") or [], ensure_ascii=False),
             json.dumps(c.get("tunnel") or {}, ensure_ascii=False)))
    conn.execute("DROP TABLE connections")
    conn.execute("ALTER TABLE connections_new RENAME TO connections")


def conns_load():
    """全量连接 -> [record]"""
    init_db()
    def _load(conn):
        rows = conn.execute(
            "SELECT name, db_type, server, port, database, uid, pwd_enc, mode,"
            " visible_to, tunnel FROM connections").fetchall()
        out = []
        for r in rows:
            (name, db_type, server, port, database, uid, pwd_enc, mode,
             vt, tunnel) = r
            rec = {"name": name, "db_type": db_type, "server": server,
                   "port": port, "database": database, "uid": uid,
                   "pwd_enc": pwd_enc, "mode": mode}
            try:
                rec["visible_to"] = json.loads(vt) if vt else []
            except Exception:
                rec["visible_to"] = []
            try:
                rec["tunnel"] = json.loads(tunnel) if tunnel else {}
            except Exception:
                rec["tunnel"] = {}
            out.append(rec)
        return out
    try:
        return _tx(_load)
    except Exception:
        return []


def conns_save(items):
    """全量覆盖写入(拆解记录写列)"""
    init_db()
    def _save(conn):
        conn.execute("DELETE FROM connections")
        for c in items:
            conn.execute(
                "INSERT INTO connections(name, db_type, server, port, database, uid,"
                " pwd_enc, mode, visible_to, tunnel) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (c.get("name", ""), c.get("db_type", ""), c.get("server", ""),
                 c.get("port", ""), c.get("database", ""), c.get("uid", ""),
                 c.get("pwd_enc", ""), c.get("mode", ""),
                 json.dumps(c.get("visible_to") or [], ensure_ascii=False),
                 json.dumps(c.get("tunnel") or {}, ensure_ascii=False)))
    _tx(_save)


def migrate_conns_json(json_path):
    """旧 connections.json -> SQLite(仅当 SQLite 无连接且 json 存在); 成功后 json 改名 .bak"""
    init_db()
    if not os.path.exists(json_path):
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("connections", []) if isinstance(data, dict) else (data or [])
        if not isinstance(items, list) or not items:
            return False
        if conns_load():
            return False
        conns_save(items)
        os.replace(json_path, json_path + ".bak")
        return True
    except Exception:
        return False


# ----------------------------- 审计日志(可 SQL 查询) -----------------------------

# 审计表保留上限(行, 优化路线图 0.1): 超上限自动清理最旧记录, 防无限增长(与文件 audit.log 10 代轮转对齐)
MAX_AUDIT_ROWS = 100000
# 清理降频: 每 N 次写入才触发一次 COUNT+DELETE(高频审计下避免额外开销)
_AUDIT_PRUNE_EVERY = 100
_AUDIT_COUNT = 0


def audit_add(ip, action, detail="", user=""):
    """追加一条审计记录(SQLite 表, 与 audit.log 文件双写); 超 MAX_AUDIT_ROWS 自动清理最旧"""
    init_db()
    try:
        def _add(conn):
            conn.execute("INSERT INTO audit_log(ts, ip, action, detail, username)"
                         " VALUES(?,?,?,?,?)",
                         (time.strftime("%Y-%m-%d %H:%M:%S"),
                          ip or "", action or "", detail or "", user or "-"))
        _tx(_add)
        _prune_audit()
    except Exception:
        pass  # 审计失败不影响主流程


def _prune_audit():
    """审计表保留上限清理(0.1): 行数超 MAX_AUDIT_ROWS 时删除最旧(id 最小)超出部分。
    每 _AUDIT_PRUNE_EVERY 次写入执行一次, 避免每次写入都跑 COUNT+DELETE。"""
    global _AUDIT_COUNT
    _AUDIT_COUNT += 1
    if _AUDIT_COUNT < _AUDIT_PRUNE_EVERY:
        return
    _AUDIT_COUNT = 0
    try:
        def _prune(conn):
            cnt = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            if cnt > MAX_AUDIT_ROWS:
                row = conn.execute(
                    "SELECT id FROM audit_log ORDER BY id DESC LIMIT 1 OFFSET ?",
                    (MAX_AUDIT_ROWS,)).fetchone()
                if row:
                    conn.execute("DELETE FROM audit_log WHERE id <= ?", (row[0],))
        _tx(_prune)
    except Exception:
        pass  # 清理失败不影响主流程


def audit_query(user=None, action=None, limit=200, offset=0):
    """审计查询: 按 用户/操作 筛选, 时间倒序; 返回行列表(供管理面板/系统查询)"""
    init_db()
    def _q(conn):
        sql = "SELECT id, ts, ip, action, detail, username FROM audit_log WHERE 1=1"
        args = []
        if user:
            sql += " AND username = ?"
            args.append(user)
        if action:
            sql += " AND action = ?"
            args.append(action)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        args += [int(limit), int(offset)]
        cur = conn.execute(sql, args)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    try:
        return _tx(_q)
    except Exception:
        return []


def audit_import_file(path):
    """把旧 logs/audit.log 历史导入 audit_log 表(仅当表空); 行格式: 时间 | IP | 操作 | 详情 | 用户"""
    init_db()
    if not os.path.exists(path):
        return 0
    try:
        def _check(conn):
            return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        if _tx(_check) > 0:
            return 0
        n = 0
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        def _import(conn):
            nonlocal n
            for line in lines:
                parts = [p.strip() for p in line.strip().split("|")]
                if len(parts) >= 3:
                    ts, ip = parts[0], parts[1]
                    user = parts[2] if len(parts) > 2 else "-"
                    action = parts[3] if len(parts) > 3 else ""
                    detail = "|".join(parts[4:]) if len(parts) > 4 else ""
                    conn.execute("INSERT INTO audit_log(ts, ip, action, detail, username)"
                                 " VALUES(?,?,?,?,?)", (ts, ip, user, action, detail))
                    n += 1
        _tx(_import)
        return n
    except Exception:
        return 0


# ----------------------------- 调度任务 -----------------------------

def tasks_load():
    """全量任务 -> [dict]"""
    init_db()
    def _load(conn):
        rows = conn.execute(
            "SELECT id, name, action, conn_name, interval_min, enabled,"
            " last_run, next_run, last_result, created_at FROM tasks ORDER BY id").fetchall()
        out = []
        for r in rows:
            (tid, name, action, conn_name, interval, enabled,
             last_run, next_run, last_result, created_at) = r
            out.append({"id": tid, "name": name, "action": action,
                        "conn_name": conn_name, "interval_min": interval,
                        "enabled": bool(enabled),
                        "last_run": last_run, "next_run": next_run,
                        "last_result": last_result or None,
                        "created_at": created_at})
        return out
    try:
        return _tx(_load)
    except Exception:
        return []


def tasks_save(tasks):
    """全量覆盖写入"""
    init_db()
    def _save(conn):
        conn.execute("DELETE FROM tasks")
        for t in tasks:
            conn.execute(
                "INSERT INTO tasks(id, name, action, conn_name, interval_min, enabled,"
                " last_run, next_run, last_result, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (t.get("id"), t.get("name", ""), t.get("action", "backup"),
                 t.get("conn_name", ""), int(t.get("interval_min", 60) or 60),
                 1 if t.get("enabled") else 0,
                 t.get("last_run"), t.get("next_run"),
                 t.get("last_result") or "", t.get("created_at")))
    _tx(_save)


def migrate_tasks_json(json_path):
    """旧 tasks.json -> SQLite(仅当表空且 json 存在); 成功后 json 改名 .bak"""
    init_db()
    if not os.path.exists(json_path):
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            return False
        if tasks_load():
            return False
        tasks_save(data)
        os.replace(json_path, json_path + ".bak")
        return True
    except Exception:
        return False


# ----------------------------- 系统查询(供后续步骤/内置系统库使用) -----------------------------

def query(sql, params=()):
    """只读 SQL 查询(供内置系统库/后续审计查询使用); 返回 [{col: value}], 最多 2000 行(防爆)"""
    init_db()
    def _q(conn):
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(2000)
        return [dict(zip(cols, row)) for row in rows]
    try:
        return _tx(_q)
    except Exception:
        raise
