# -*- coding: utf-8 -*-
"""dbmanager - 入口模块
启动服务器（IPv4+IPv6 双栈、可选 HTTPS、端口占用检测、自动打开浏览器）。

模块结构（依赖方向自上而下，无循环导入）:
  config.py    配置与共享状态（常量/路径/缓存容器/线程锁/驱动选择）
  crypto.py    密码加解密（AES-GCM 落盘 / RSA 传输 / DPAPI）
  store.py     连接配置持久化（connections.json 原子写）
  dbcore.py    引擎管理（URL 构建/引擎缓存/超时/连接测试/事务连接）
  ops.py       数据操作层（元数据/数据/CRUD/SQL 控制台/导入导出/同步）
  handler.py   HTTP 层（会话/网关令牌/HTTPS/静态资源/API 路由）
  app.py       入口（服务器类/SSL 组装/启动流程）

启动: python app.py
"""
import http.server
import os
import re
import socket
import sys
import threading
import time
import webbrowser

import config
from config import HOST, PORT
import logging_conf
logging_conf.setup_logging()  # 结构化日志: 控制台 + logs/dbmanager.log(必须先于 handler/crypto 的日志输出)
import logging
import handler
from handler import Handler
import auth  # 账号体系: ensure_default 幂等创建/迁移(默认 admin 角色升级)

logger = logging.getLogger("app")


class ResilientHTTPServer(http.server.ThreadingHTTPServer):
    """accept / 处理阶段的异常不应杀死整个监听线程。

    默认 ThreadingHTTPServer.handle_request 只在 get_request 捕获 OSError，
    其它异常（如 SSL 握手异常、被端口转发进来的异常流量）会穿透 serve_forever，
    使该监听线程退出，导致对应协议栈（IPv4 或 IPv6）悄无声息地停止 accept，
    外层主线程因另一个线程仍存活而不会退出进程，表现为“端口 LISTENING 却连不上”。
    这里把 accept 阶段的异常全部吞掉，并在主循环里自动重启死掉的线程。"""

    def handle_request(self):
        try:
            request, client_address = self.get_request()
        except Exception:
            return
        if self.verify_request(request, client_address):
            try:
                self.process_request(request, client_address)
            except Exception:
                self.handle_error(request, client_address)
                self.shutdown_request(request)
            except BaseException:
                self.shutdown_request(request)
                raise
        else:
            self.shutdown_request(request)


class IPv6Server(ResilientHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        # Windows 上 :: 默认双栈（v6only=False），会吞掉 IPv4 流量导致独立的
        # 0.0.0.0 监听变成僵尸（LISTENING 却不 accept）。显式设 v6only=1，
        # 让 IPv6 与 IPv4 两个 socket 干净分离、各自独立工作。
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        except Exception:
            pass
        super().server_bind()


def _port_in_use(port):
    """检测端口是否已有服务监听, 用于防止重复启动导致连接配置并发覆盖"""
    for host in ("127.0.0.1", "::1"):
        s = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET)
        s.settimeout(0.8)
        try:
            s.connect((host, port))
            return True
        except Exception:
            pass
        finally:
            s.close()
    return False

def _kill_old_instance(port):
    """自动接管: 占用端口的进程若为 dbmanager 旧实例(app.py)则杀掉, 返回是否已释放。
    仅杀命令行含 app.py 的进程(避免误杀其他程序); 非 dbmanager / 权限不足 / DBM_NO_KILL=1 时返回 False(维持原提示)。"""
    if config.conf("DBM_NO_KILL"):
        return False
    import subprocess
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"],
                                          text=True, errors="ignore", timeout=10)
            pids = set()
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line.upper():
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        pids.add(parts[-1])
            if not pids:
                return False
            for pid in pids:
                try:
                    ps = ("Get-CimInstance Win32_Process -Filter 'ProcessId = %s' "
                          "| Select-Object -ExpandProperty CommandLine" % pid)
                    cmd = subprocess.check_output(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                        text=True, errors="ignore", timeout=8,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except Exception:
                    cmd = ""
                if "app.py" in cmd.lower():
                    try:
                        subprocess.run(["taskkill", "/PID", pid, "/F"],
                                       capture_output=True, timeout=8)
                    except Exception:
                        pass
        else:
            # Linux/macOS: fuser 找到占用端口的进程, 确认是 app.py 再 kill
            try:
                out = subprocess.run(["fuser", "-v", f"{port}/tcp"],
                                     capture_output=True, text=True, timeout=8)
                if out.returncode == 0:
                    pids = re.findall(r"\b(\d+)\b", out.stderr or "")
                    for pid in pids:
                        cmd = ""
                        try:
                            with open(f"/proc/{pid}/cmdline", "rb") as f:
                                cmd = f.read().decode(errors="ignore").replace("\x00", " ")
                        except Exception:
                            try:
                                cmd = subprocess.check_output(["ps", "-p", pid, "-o", "command="],
                                                             text=True, errors="ignore", timeout=5)
                            except Exception:
                                cmd = ""
                        if "app.py" in cmd:
                            subprocess.run(["kill", "-9", pid], capture_output=True, timeout=8)
            except FileNotFoundError:
                return False
        time.sleep(1)
        return not _port_in_use(port)
    except Exception:
        return False

def run():
    _created = auth.ensure_default()  # 幂等: 创建默认 admin(admin 角色) + 旧部署自动升级 admin 角色
    # 审计历史导入(SQLite audit_log 表, 仅首次/表空时) + 旧 tasks.json 迁移
    try:
        import sqlitedb
        sqlitedb.audit_import_file(os.path.join(config.BASE_DIR, "logs", "audit.log"))
        sqlitedb.migrate_tasks_json(os.path.join(config.BASE_DIR, "tasks.json"))
    except Exception:
        pass
    if _created or auth.is_default_pwd():
        logger.warning("=" * 64)
        logger.warning("安全提醒: 默认管理员口令仍为默认值(admin123 / DBM_DEFAULT_PWD), 存在弱口令风险!")
        logger.warning("请立即登录后修改默认密码(或删除默认账号); LAN/公网部署务必处理。")
        logger.warning("=" * 64)
    import task_sched
    task_sched.start()  # 启动调度线程(定时备份任务, P2-2)
    if _port_in_use(PORT):
        if _kill_old_instance(PORT):
            logger.warning(f"端口 {PORT} 已被旧实例占用, 已自动终止旧实例并接管端口。")
            sys.stdout.flush()
        else:
            logger.warning("=" * 64)
            logger.warning(f"端口 {PORT} 已被占用: 似乎已有一个 DB Manager 实例在运行。")
            logger.warning("为避免连接配置被并发覆盖, 已拒绝重复启动。")
            logger.warning("若确认是旧实例(命令行含 app.py), 将自动接管; 若为其他程序占用,")
            logger.warning("请手动释放端口(设置 DBM_NO_KILL=1 可关闭自动终止)。")
            logger.warning("=" * 64)
            sys.stdout.flush()
            return
    servers = []
    try:
        # 绑定策略: 安全默认仅本机(config.HOST=127.0.0.1, 五轮评估 P2-1 收敛暴露面);
        # 需局域网/公网访问显式 DBM_HOST=0.0.0.0(此时同时监听 IPv4+IPv6)
        if HOST in ("0.0.0.0", "::"):
            servers.append(ResilientHTTPServer(("0.0.0.0", PORT), Handler))
            try:
                servers.append(IPv6Server(("::", PORT), Handler))
            except Exception as e:
                logger.error("注：IPv6(::) 监听启动失败，仅 IPv4 可用：%s", e)
                sys.stdout.flush()
        elif ":" in HOST:
            servers.append(IPv6Server((HOST, PORT), Handler))
        else:
            servers.append(ResilientHTTPServer((HOST, PORT), Handler))
    except Exception as e:
        logger.error("启动失败：%s", e)
        sys.stdout.flush()
        return
    # SSL / HTTPS（DBM_SSL_CERT/DBM_SSL_KEY 显式证书，或 DBM_SSL=1 自动生成自签名证书）
    ssl_on = handler._ssl_setup()
    if ssl_on:
        try:
            import ssl as _ssl
            ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(handler.SSL_CERT, handler.SSL_KEY)
            ctx.options |= _ssl.OP_NO_SSLv2 | _ssl.OP_NO_SSLv3
            try:
                ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5")
            except Exception:
                pass
            for s in servers:
                s.socket = ctx.wrap_socket(s.socket, server_side=True, do_handshake_on_connect=False)
            logger.info("已启用 HTTPS（证书：%s）", handler.SSL_CERT)
        except Exception as e:
            logger.error("SSL 启用失败，回退为 HTTP：%s", e)
            import traceback; traceback.print_exc()
            sys.stdout.flush()
            ssl_on = False
    # 传输安全提醒(五轮评估 P2-1 补全): 明文 HTTP 且绑定非回环地址时,
    # 会话令牌/网关令牌可被局域网嗅探劫持。默认 HOST=127.0.0.1 不触发;
    # 仅当用户显式 DBM_HOST=非回环 且未启用 HTTPS 时提醒, 引导启用 DBM_SSL=1。
    if not ssl_on and HOST not in ("127.0.0.1", "::1", "localhost"):
        logger.warning("=" * 64)
        logger.warning("安全提醒: 当前以明文 HTTP 监听非回环地址(%s), 会话令牌存在被局域网嗅探劫持的风险!", HOST)
        logger.warning("公网/局域网多用户部署强烈建议启用 HTTPS: 设置 DBM_SSL=1 自动生成自签名证书,")
        logger.warning("或提供自有证书(DBM_SSL_CERT / DBM_SSL_KEY)。")
        logger.warning("=" * 64)
    config.SERVERS = servers
    url = ("https" if ssl_on else "http") + f"://127.0.0.1:{PORT}"
    logger.info("DB Manager 多数据库版运行在 %s", url)
    logger.info("监听：%s:%s（HTTPS=%s）", HOST, PORT, "on" if ssl_on else "off")
    logger.info("公网访问需先输入网关令牌；内网/回环/链路本地免验证。")
    sys.stdout.flush()
    threads = []
    for s in servers:
        t = threading.Thread(target=s.serve_forever, daemon=True)
        t.start()
        threads.append(t)
    # 自动打开浏览器（dbmanager.conf [server] no_open=1 或 DBM_NO_OPEN=1 可禁用）
    if not config.conf("DBM_NO_OPEN"):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        while True:
            for i, t in enumerate(threads):
                if not t.is_alive():
                    logger.warning("监听线程 #%s 已退出，正在重启……", i)
                    sys.stdout.flush()
                    nt = threading.Thread(target=servers[i].serve_forever, daemon=True)
                    nt.start()
                    threads[i] = nt
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            try:
                s.server_close()
            except Exception:
                pass

if __name__ == "__main__":
    run()
