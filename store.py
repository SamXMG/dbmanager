# -*- coding: utf-8 -*-
"""dbmanager - 连接配置持久化
connections.json 的读写(原子写), 密码字段保持密文。
"""
import json
import os

from config import DEFAULT_PORT, SUPPORTED
from crypto import _conn_file, decrypt_pwd, encrypt_pwd


def _load_conn_store():
    """读取连接存储。文件损坏时抛异常(绝不静默返回 [] 导致保存时覆盖丢失全部连接)"""
    cf = _conn_file()
    if not os.path.exists(cf):
        return []
    with open(cf, "r", encoding="utf-8") as _f:
        data = json.load(_f)
    return data.get("connections", []) if isinstance(data, dict) else (data or [])

def _save_conn_store(items):
    """原子写连接存储: 先写临时文件再 os.replace, 避免写一半崩溃损坏文件"""
    cf = _conn_file()
    tmp = cf + ".tmp"
    with open(tmp, "w", encoding="utf-8") as _f:
        json.dump({"connections": items}, _f, ensure_ascii=False, indent=2)
    os.replace(tmp, cf)

def list_connections():
    """返回连接列表（不含密码，仅 has_pwd 标记）"""
    out = []
    for c in _load_conn_store():
        out.append({
            "name": c.get("name"),
            "db_type": c.get("db_type"),
            "server": c.get("server"),
            "port": c.get("port"),
            "database": c.get("database", ""),
            "uid": c.get("uid", ""),
            "has_pwd": bool(c.get("pwd_enc")),
            "visible_to": c.get("visible_to") or [],   # 内网 ACL: 可见用户列表(空=所有人)
            "mode": c.get("mode", ""),                  # read_only: 生产库强制只读标记
        })
    return out

def save_connection(conn):
    """新增或更新一条连接；pwd 为明文，自动加密后存储"""
    name = (conn.get("name") or "").strip()
    if not name:
        raise ValueError("连接名称不能为空")
    db_type = (conn.get("db_type") or "").lower()
    if db_type not in SUPPORTED:
        raise ValueError(f"不支持的数据库类型: {db_type}")
    items = _load_conn_store()
    rec = {
        "name": name,
        "db_type": db_type,
        "server": conn.get("server", ""),
        "port": conn.get("port") or DEFAULT_PORT.get(db_type) or "",
        "database": conn.get("database", ""),
        "uid": conn.get("uid", ""),
        "pwd_enc": encrypt_pwd(conn.get("pwd", "")),
        # 内网 ACL: 可见用户列表(空=所有人); mode=read_only 生产库强制只读(仅 admin 可设)
        "visible_to": conn.get("visible_to") or [],
        "mode": "read_only" if conn.get("mode") == "read_only" else "",
    }
    # SSH 隧道配置: 密码同样加密存储(密钥路径明文)
    t = conn.get("tunnel")
    if t and t.get("host"):
        rec["tunnel"] = {
            "host": t.get("host", ""),
            "port": t.get("port") or 22,
            "user": t.get("user", ""),
            "password": encrypt_pwd(t.get("password", "")),
            "key": t.get("key", ""),
        }
    for i, c in enumerate(items):
        if c.get("name") == name:
            items[i] = rec
            break
    else:
        items.append(rec)
    _save_conn_store(items)
    return rec

def delete_connection(name):
    items = _load_conn_store()
    new = [c for c in items if c.get("name") != name]
    if len(new) == len(items):
        raise ValueError(f"未找到连接: {name}")
    _save_conn_store(new)
    return True

def get_connection_by_name(name):
    for c in _load_conn_store():
        if c.get("name") == name:
            rec = dict(c)
            try:
                rec["pwd"] = decrypt_pwd(c.get("pwd_enc", ""))
            except Exception:
                raise ValueError(
                    f"连接「{name}」的密码无法解密(可能是旧密钥加密的)。"
                    f"请编辑该连接重新输入密码并保存。")
            rec.pop("pwd_enc", None)
            # SSH 隧道密码同样解密为明文供建隧道使用
            if rec.get("tunnel") and rec["tunnel"].get("password"):
                try:
                    rec["tunnel"]["password"] = decrypt_pwd(rec["tunnel"]["password"])
                except Exception:
                    rec["tunnel"]["password"] = ""
            return rec
    return None
