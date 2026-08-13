# -*- coding: utf-8 -*-
"""dbmanager - 数据库引擎与连接管理
URL 构建、引擎缓存(上限32)、超时设置、连接测试、事务模式持久连接。
"""
import hashlib
import os
from urllib.parse import quote, quote_plus

from sqlalchemy import create_engine, text

import config
from config import (
    CONN_IDLE_TIMEOUT, DEFAULT_DRIVER, DEFAULT_PORT, ENGINE_CACHE,
    ENGINE_CACHE_MAX, LOCK, QUERY_TIMEOUT, TX_CONN,
    DB_POOL_SIZE, DB_POOL_MAX_OVERFLOW, DB_POOL_TIMEOUT,
    _mysql_scheme, _odbc_drivers, _pick_mssql_driver,
)

# ------------------------------
# 连接串 / 引擎
# ------------------------------
def build_url(ci: dict) -> str:
    """根据数据库类型构造 SQLAlchemy URL"""
    ci = _norm_db_type(ci)
    t = (ci.get("db_type") or "mssql").lower()
    if t == "mysql" and "\\" in (ci.get("server") or ""):
        raise ValueError("服务器地址含实例名(主机\\实例),这通常是 SQL Server 连接。"
                         "请把「数据库类型」切换为 SQL Server 后再测试。")
    if t == "sqlite":
        db = (ci.get("database") or ":memory:").strip()
        if db == ":memory:":
            return "sqlite:///:memory:"
        # 路径沙箱: 校验解析后不逃逸允许根(防 ../../ 读取系统文件); 校验通过后用原始 db 组装 URL
        _safe_sqlite_path(db)
        if os.path.isabs(db):
            # 绝对路径: 反斜杠转正斜杠以兼容 SQLAlchemy sqlite URL 解析
            return "sqlite:///" + quote(db.replace("\\", "/"), safe="/:")
        # 相对路径: 保持相对, 由 sqlite 按 cwd 解析(兼容中文目录与历史约定)
        return "sqlite:///" + quote(db, safe="/:\\")
    user = quote_plus(ci.get("uid") or "")
    pwd = quote_plus(ci.get("pwd") or "")
    host = ci.get("server") or "localhost"
    port = ci.get("port") or DEFAULT_PORT.get(t) or ""
    dbn = ci.get("database") or ""
    if t == "mssql" and "\\" in host:
        port = ""  # 命名实例(host\instance): 端口由 SQL Browser(1434)动态解析, 不能固定为 1433
    netloc = f"{host}:{port}" if port else host
    if t == "mysql":
        return f"{_mysql_scheme()}://{user}:{pwd}@{netloc}/{dbn}"
    if t == "postgresql":
        return f"postgresql+pg8000://{user}:{pwd}@{netloc}/{dbn}"
    if t == "oracle":
        # python-oracledb thin 模式(纯 Python, 无需 Oracle Client); database 字段填 service_name
        if dbn:
            return f"oracle+oracledb://{user}:{pwd}@{netloc}/?service_name={quote_plus(dbn)}"
        return f"oracle+oracledb://{user}:{pwd}@{netloc}/"
    if t == "mssql":
        drv = ci.get("driver") or DEFAULT_DRIVER
        if drv not in _odbc_drivers():
            picked = _pick_mssql_driver()
            if picked:
                drv = picked  # 用户指定/默认驱动不存在时, 自动降级到本机可用驱动
            else:
                raise ValueError(
                    "未找到 SQL Server ODBC 驱动。请安装微软 "
                    "'ODBC Driver 17/18 for SQL Server'(注意位数需与 Python 一致: "
                    "64 位 Python 需 64 位驱动), 或确认已安装 pyodbc。"
                    "当前 pyodbc 可见驱动: " + (", ".join(_odbc_drivers()) or "(无)"))
        if not dbn:
            dbn = "master"  # 空库默认 master: 规避 SQLAlchemy 空库时把 host 当 DSN 导致的 IM002
        drv_enc = drv.replace(" ", "+")
        return (f"mssql+pyodbc://{user}:{pwd}@{netloc}/{dbn}"
                f"?driver={drv_enc}&TrustServerCertificate=yes&Encrypt=no")
    raise ValueError(f"不支持的数据库类型: {t}")


def is_safe_server(srv: str) -> bool:
    """SSRF 防护: server 必须为合法主机名/IP(可选 :端口), 拒绝 URL/路径形式与云元数据/链路本地地址。
    返回 True 表示安全。供 /api/test 与 /api/connect 复用。
    注意: 回环(127.0.0.1/localhost)与内网地址(RFC1918)为合法 DB 地址, 不过滤, 以免破坏本地/内网库连接。"""
    if not srv:
        return False
    s = str(srv).strip()
    if "://" in s or s.startswith(("/", "\\")):
        return False
    low = s.lower()
    # 云元数据 / 链路本地(SSRF 经典靶标): 169.254.0.0/16, 含 169.254.169.254
    if low.startswith("169.254.") or low == "169.254.169.254":
        return False
    # 0.0.0.0 作为目标地址无意义(监听通配), 视为非法
    if low == "0.0.0.0":
        return False
    # IPv6 兜底 (优秀判定 P2-1): 与 IPv4 同策略——
    # 链路本地 fe80::/10 ≈ 169.254(拒绝); ULA fc00::/7 ≈ RFC1918 内网(放行); 回环 ::1 放行;
    # IPv4-mapped(::ffff:x.x.x.x) 检查映射的 IPv4 是否元数据/通配。
    v6 = low.split("%", 1)[0].strip().strip("[]")
    if ":" in v6:
        try:
            import ipaddress
            ip = ipaddress.IPv6Address(v6)
        except ValueError:
            return True  # 非 IPv6 字面量(主机名:端口等), 走原放行逻辑
        # 注意顺序: Python 的 is_private 对 IPv6 包含 fe80(链路本地), 必须先判 is_link_local
        if ip.is_link_local:
            return False
        if ip.is_loopback or ip.is_private:
            return True
        if ip.ipv4_mapped is not None:
            m4 = str(ip.ipv4_mapped)
            if m4.startswith("169.254.") or m4 == "0.0.0.0":
                return False
            return True
        return True  # 其余合法 IPv6 地址(如 2001:db8::1)放行
    return True


def _safe_sqlite_path(db: str) -> str:
    """SQLite 连接数据库路径沙箱: 仅允许落在 DATA_ROOT / 进程工作目录(cwd) / DBM_SQLITE_ALLOW_ROOTS 内,
    拒绝 ../ 逃逸读取/创建系统文件(如 /etc/passwd)。
    - DATA_ROOT(BASE_DIR/data): 推荐的数据目录;
    - cwd: 兼容历史相对路径约定(测试库/用户库常建在项目根);
    - DBM_SQLITE_ALLOW_ROOTS: 生产环境连接数据盘上的库时追加。
    相对路径按 cwd 解析(与历史 build_url 行为一致), 仅校验解析后不逃逸上述根。"""
    root = os.path.realpath(config.DATA_ROOT)
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        pass
    cwd = os.path.realpath(os.getcwd())
    cand = db if os.path.isabs(db) else os.path.join(cwd, db)
    cand = os.path.realpath(cand)
    allowed = [root, cwd]
    for r in config.SQLITE_ALLOW_ROOTS:
        allowed.append(os.path.realpath(r))
    for ar in allowed:
        if cand == ar or cand.startswith(ar + os.sep):
            return cand
    raise ValueError("SQLite 数据库路径必须落在数据目录(%s)或工作目录(%s)或额外允许根内, 拒绝访问: %s"
                     % (root, cwd, db))


def conn_hash(ci: dict) -> str:
    """连接缓存键：包含密码摘要，改密码后引擎缓存自动失效（无需重启进程）"""
    key = "|".join(str(ci.get(k) or "") for k in
                   ("db_type", "server", "port", "database", "uid", "pwd"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

# 协议兼容数据库: 前端可选这些类型, 后端统一归一化为标准引擎
DB_TYPE_ALIAS = {
    "oceanbase": "mysql",       # OceanBase MySQL 模式
    "tidb": "mysql",            # TiDB 兼容 MySQL 协议
    "kingbase": "postgresql",   # 人大金仓 KingbaseES 兼容 PG 协议
}

def _norm_db_type(ci: dict) -> dict:
    """把协议兼容类型归一化为标准类型(返回新 dict, 不修改原对象)"""
    t = (ci.get("db_type") or "").lower()
    if t in DB_TYPE_ALIAS:
        ci = dict(ci)
        ci["db_type"] = DB_TYPE_ALIAS[t]
    return ci

def _apply_query_timeout(eng, t):
    """给引擎挂方言级查询超时(连接建立时设置), 防止大查询无限卡死线程"""
    from sqlalchemy import event

    def _set(dbapi_conn, record):
        try:
            if t == "mysql":
                cur = dbapi_conn.cursor()
                cur.execute("SET SESSION MAX_EXECUTION_TIME = %d" % (QUERY_TIMEOUT * 1000))
                cur.close()
            elif t == "postgresql":
                cur = dbapi_conn.cursor()
                cur.execute("SET statement_timeout = %d" % (QUERY_TIMEOUT * 1000))
                cur.close()
            elif t == "mssql":
                dbapi_conn.timeout = QUERY_TIMEOUT  # pyodbc 连接对象的查询超时(秒)
        except Exception:
            pass

    try:
        event.listen(eng, "connect", _set)
    except Exception:
        pass

def _apply_tunnel(ci: dict) -> dict:
    """连接带 tunnel 配置时, 建立本地 SSH 端口转发并把 server/port 指向本地; 否则原样返回"""
    t = ci.get("tunnel")
    if not t or not t.get("host"):
        return ci
    try:
        from tunnel import start_tunnel
        local_port = start_tunnel(t)
    except Exception as e:
        raise ValueError("SSH 隧道建立失败: %s" % e)
    ci = dict(ci)
    ci["server"] = "127.0.0.1"
    ci["port"] = local_port
    return ci


def get_engine(ci: dict):
    """获取(并缓存)数据库引擎，附带连接测试与断线自愈; 支持 SSH 隧道(自动建本地转发)"""
    ci = _norm_db_type(ci)
    ci = _apply_tunnel(ci)
    h = conn_hash(ci)
    with LOCK:
        if h in ENGINE_CACHE:
            return ENGINE_CACHE[h]
    try:
        url = build_url(ci)
        t = (ci.get("db_type") or "mysql").lower()
        kw = {"pool_pre_ping": True, "pool_recycle": CONN_IDLE_TIMEOUT,
              "future": True, "connect_args": {}}
        if t == "sqlite":
            # 复核 P1-8: SQLite 锁等待超时 30s(默认 5s 对慢事务不够), 防慢库永久占线程
            kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            # 高并发挡板: 显式约束每个目标库的连接池并发上限与取连超时(覆盖 SQLAlchemy 默认 5/10/30)。
            # pool_size+max_overflow = 单库最大并发连接; pool_timeout 控制池满时快速失败(抛 TimeoutError→上层转 5xx),
            # 而非阻塞 30s 把请求线程占死。SQLite 用 SingletonThreadPool 不接受这些参数, 故仅非 sqlite 生效。
            kw["pool_size"] = DB_POOL_SIZE
            kw["max_overflow"] = DB_POOL_MAX_OVERFLOW
            kw["pool_timeout"] = DB_POOL_TIMEOUT
            if t == "mysql":
                kw["connect_args"] = {"connect_timeout": 8}
            elif t == "postgresql":
                kw["connect_args"] = {"connect_timeout": 8}
            elif t == "mssql":
                kw["connect_args"] = {"timeout": 8}
        eng = create_engine(url, **kw)
        if t != "sqlite":
            _apply_query_timeout(eng, t)  # 查询超时落地(默认 30s)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        raise ValueError("连接失败: " + str(e))
    with LOCK:
        if len(ENGINE_CACHE) >= ENGINE_CACHE_MAX:
            oldest_key = next(iter(ENGINE_CACHE))
            old_eng = ENGINE_CACHE.pop(oldest_key)
            try:
                old_eng.dispose()
            except Exception:
                pass
        ENGINE_CACHE[h] = eng
    return eng

def test_connection(ci: dict):
    """轻量连接测试：建临时引擎并 SELECT 1 验证，不写入 ENGINE_CACHE，失败抛异常。"""
    from sqlalchemy import create_engine, text
    ci = _norm_db_type(ci)
    ci = _apply_tunnel(ci)   # 支持 SSH 隧道
    t = (ci.get("db_type") or "mysql").lower()
    if t == "mongodb":
        get_mongo(ci)  # 内部已 ping 验证
        return
    if t == "redis":
        get_redis(ci)  # 内部已 ping 验证
        return
    url = build_url(ci)
    connect_args = {}
    if t == "mysql":
        connect_args = {"connect_timeout": 8}
    elif t == "postgresql":
        connect_args = {"connect_timeout": 8}
    elif t == "mssql":
        connect_args = {"timeout": 8}
    eng = create_engine(url, connect_args=connect_args, pool_pre_ping=False, future=True)
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
    finally:
        eng.dispose()

# MongoDB 客户端缓存(与 SQLAlchemy 引擎缓存分离; 上限同引擎)
MONGO_CACHE = {}

def get_mongo(ci: dict):
    """获取(并缓存) MongoDB 客户端; 建连即 ping 验证, 失败抛异常"""
    from pymongo import MongoClient
    ci = _apply_tunnel(ci)   # 支持 SSH 隧道
    h = conn_hash(ci)
    with LOCK:
        c = MONGO_CACHE.get(h)
        if c is not None:
            return c
    host = ci.get("server") or "localhost"
    port = int(ci.get("port") or 27017)
    kw = {"serverSelectionTimeoutMS": 8000, "connectTimeoutMS": 8000}
    uid = ci.get("uid")
    if uid:
        kw["username"] = uid
        kw["password"] = ci.get("pwd") or ""
        auth = (ci.get("database") or "").strip()
        if auth:
            kw["authSource"] = auth
    client = MongoClient(host, port, **kw)
    try:
        client.admin.command("ping")   # 立即验证可达性, 避免惰性连接掩盖错误
    except Exception:
        try:
            client.close()
        except Exception:
            pass
        raise
    with LOCK:
        if len(MONGO_CACHE) >= ENGINE_CACHE_MAX:
            MONGO_CACHE.pop(next(iter(MONGO_CACHE)), None)
        MONGO_CACHE[h] = client
    return client

# Redis 客户端缓存
REDIS_CACHE = {}

def get_redis(ci: dict):
    """获取(并缓存) Redis 客户端; 建连即 ping 验证, 失败抛异常"""
    import redis as redis_mod
    ci = _apply_tunnel(ci)   # 支持 SSH 隧道
    h = conn_hash(ci)
    with LOCK:
        c = REDIS_CACHE.get(h)
        if c is not None:
            return c
    host = ci.get("server") or "localhost"
    port = int(ci.get("port") or 6379)
    try:
        from redis.backoff import ExponentialBackoff
        from redis.retry import Retry
        _retry = Retry(ExponentialBackoff(0.5), 1)   # 连接失败快速报错(共2次尝试)
    except Exception:
        _retry = None
    r = redis_mod.Redis(host=host, port=port, password=ci.get("pwd") or None,
                        db=int((ci.get("database") or "0") or 0),
                        socket_connect_timeout=5, socket_timeout=8,
                        decode_responses=True, retry_on_timeout=False,
                        protocol=2,   # RESP2: 兼容 Redis 5(无 HELLO 命令), 对 6/7 无副作用
                        **(dict(retry=_retry) if _retry else {}))
    try:
        r.ping()   # 立即验证可达性
    except Exception:
        try:
            r.close()
        except Exception:
            pass
        raise
    with LOCK:
        if len(REDIS_CACHE) >= ENGINE_CACHE_MAX:
            REDIS_CACHE.pop(next(iter(REDIS_CACHE)), None)
        REDIS_CACHE[h] = r
    return r

def get_connection(ci: dict, use_tx: bool = False, tx_key: str = ""):
    """获取连接；事务模式下按 (连接, tx_key) 复用独立事务连接(多标签页互不干扰)"""
    engine = get_engine(ci)
    if not use_tx:
        return engine.connect()
    key = (conn_hash(ci), tx_key or "")
    with LOCK:
        item = TX_CONN.get(key)
        if item:
            conn = item[0]
            try:
                conn.execute(text("SELECT 1"))
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                TX_CONN.pop(key, None)
                item = None
        if not item:
            conn = engine.connect()
            conn.begin()
            TX_CONN[key] = (conn, engine)
    return TX_CONN[key][0]
