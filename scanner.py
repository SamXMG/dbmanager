# -*- coding: utf-8 -*-
"""dbmanager - scanner: 本机 Navicat 保存连接扫描(优化路线图 1.1 handler 拆分)。
从 handler.py 独立, 纯 socket/文件扫描, 无 handler 依赖。"""
import os
import sqlite3

from config import DEFAULT_PORT


def _navicat_base():
    """返回 Navicat 连接目录（Documents\\Navicat 或 Documents\\PremiumSoft）"""
    for sub in ("Navicat", "PremiumSoft"):
        p = os.path.join(os.path.expanduser("~"), "Documents", sub)
        if os.path.isdir(p):
            return p
    return None


_NAV_TYPE_MAP = {
    "mysql": "mysql", "mariadb": "mysql", "postgresql": "postgresql",
    "sql server": "mssql", "sqlite": "sqlite", "oracle": "oracle",
}


def discover_navicat_connections():
    """扫描 Navicat 保存的连接，返回 [{name, db_type, server, port, databases}]。
    连接信息来自 Documents\\Navicat\\<类型>\\Servers\\<连接名> 目录；
    <连接名> 形如 host_port 时可解析出地址，否则默认本机 + 该类型默认端口。
    每个连接目录下的 id_cache.db(SQLite) 记录了曾访问过的库名，用于预填。"""
    base = _navicat_base()
    out = []
    if not base:
        return out
    try:
        types = os.listdir(base)
    except Exception:
        return out
    for ftype in types:
        srv_dir = os.path.join(base, ftype, "Servers")
        if not os.path.isdir(srv_dir):
            continue
        db_type = _NAV_TYPE_MAP.get(ftype.lower(), ftype.lower())
        try:
            names = os.listdir(srv_dir)
        except Exception:
            continue
        for name in names:
            conn_dir = os.path.join(srv_dir, name)
            if not os.path.isdir(conn_dir):
                continue
            host, port = None, None
            if "_" in name:
                maybe_host, _, maybe_port = name.rpartition("_")
                if maybe_port.isdigit():
                    host, port = maybe_host, int(maybe_port)
            if host is None:
                # 连接别名（如 mariadb/LocalDB），文件夹名未编码地址，host 未知，留空让用户填，不猜测 localhost
                host = ""
                port = DEFAULT_PORT.get(db_type)
            dbs = []
            cache = os.path.join(conn_dir, "id_cache.db")
            if os.path.isfile(cache):
                try:
                    c = sqlite3.connect(cache)
                    rows = c.execute(
                        "SELECT DISTINCT ObjectName FROM IdentifierCache "
                        "WHERE ObjectType IN ('Schema','Catalog') AND ObjectName<>'' "
                        "ORDER BY 1"
                    ).fetchall()
                    dbs = [r[0] for r in rows]
                    c.close()
                except Exception:
                    pass
            out.append({
                "name": name,
                "db_type": db_type,
                "server": host,
                "port": port,
                "databases": dbs,
            })
    return out
