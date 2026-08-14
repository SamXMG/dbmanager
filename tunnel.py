# -*- coding: utf-8 -*-
"""SSH 隧道: paramiko TCP 端口转发, 数据库连接可经跳板机(SSH)访问内网数据库。
用法: 连接配置带 tunnel={host,port,user,password|key,remote_host,remote_port} 时,
get_engine/build_url 前调用 start_tunnel 建立本地随机端口转发, 连接指向 127.0.0.1:本地端口。
同一 SSH 配置复用同一隧道(按 key), 服务退出时进程结束自动释放。"""
import socket
import threading

import paramiko  # type: ignore[import-untyped]

_TUNNELS: dict[str, tuple] = {}          # key -> (client, local_port)
_LOCK = threading.Lock()


def _tunnel_key(cfg):
    return "%s:%s@%s" % (cfg.get("user", ""), cfg.get("port", 22), cfg.get("host", ""))


def start_tunnel(cfg):
    """建立 SSH 端口转发: 本地随机端口 -> 远端 remote_host:remote_port; 返回本地端口"""
    if not cfg or not cfg.get("host"):
        raise ValueError("SSH 隧道配置不完整(缺少 host)")
    remote = (cfg.get("remote_host") or "127.0.0.1", int(cfg.get("remote_port") or 3306))
    key = _tunnel_key(cfg)
    with _LOCK:
        if key in _TUNNELS:
            return _TUNNELS[key][1]   # 已存在复用

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if cfg.get("key"):
            kf = cfg["key"]
            try:
                pkey = paramiko.Ed25519Key.from_private_key_file(kf)
            except Exception:
                pkey = paramiko.RSAKey.from_private_key_file(kf)
            client.connect(cfg["host"], int(cfg.get("port") or 22), cfg.get("user") or "",
                           pkey=pkey, timeout=12, banner_timeout=15)
        else:
            client.connect(cfg["host"], int(cfg.get("port") or 22), cfg.get("user") or "",
                           cfg.get("password") or "", timeout=12, banner_timeout=15)
    except Exception as e:
        try:
            client.close()
        except Exception:
            pass
        raise ValueError("SSH 连接失败: %s" % e)

    transport = client.get_transport()
    # 本地监听随机端口
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    local_port = probe.getsockname()[1]
    probe.close()

    def pump(src, dst):
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass

    def handle(conn):
        try:
            chan = transport.open_channel("direct-tcpip", remote, ("127.0.0.1", local_port))
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return
        threading.Thread(target=pump, args=(conn, chan), daemon=True).start()
        threading.Thread(target=pump, args=(chan, conn), daemon=True).start()

    def accept_loop():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", local_port))
        srv.listen(16)
        while True:
            try:
                c, _ = srv.accept()
            except Exception:
                break
            threading.Thread(target=handle, args=(c,), daemon=True).start()
        try:
            srv.close()
        except Exception:
            pass

    threading.Thread(target=accept_loop, daemon=True).start()
    with _LOCK:
        _TUNNELS[key] = (client, local_port)
    return local_port


def stop_tunnel(cfg):
    """关闭指定 SSH 配置的隧道"""
    key = _tunnel_key(cfg)
    with _LOCK:
        item = _TUNNELS.pop(key, None)
    if item:
        try:
            item[0].close()
        except Exception:
            pass
