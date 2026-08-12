# -*- coding: utf-8 -*-
"""dbmanager - HTTP 处理层
会话(SESSIONS)、网关令牌鉴权、HTTPS/自签证书、静态资源服务、
以及全部 API 路由(Handler 类)。
"""
import base64
import datetime
import functools
import hashlib
import http.server
import ipaddress
import json
import logging
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse

import config
import auth  # 账号体系（users.json; 不存在则整体不启用）

logger = logging.getLogger("handler")
from config import (
    DEFAULT_PORT, HOST, PORT, SESSIONS, SESSION_TTL, STATIC_DIRS,
)
from crypto import maybe_decrypt_pwd, rsa_public_pem
from dbcore import _norm_db_type, test_connection
from store import (
    delete_connection, get_connection_by_name, list_connections, save_connection,
)
from routes import ROUTE_MODS
from ops import (
    _xlsx_bytes, alter_table, backup_database, commit_transaction, diff_schema,
    drop_routine, execute_routine, execute_schema_sync, explain_query, export_data,
    export_schema_doc,
    get_columns, get_data, get_databases, get_er_data, get_indexes, get_relations,
    get_routine_params, get_routine_source, get_routines, get_tables, get_users_privs,
    import_data, mutate, parse_xlsx_import, restore_sql, rollback_transaction,
    run_sql, save_routine, stats_column, gen_data, sync_table, transfer_data,
)
import task_sched  # 简单调度器(P2-2): 定时备份任务

def parse_conn_header(handler):
    raw = handler.headers.get("X-Conn")
    if not raw:
        raise ValueError("缺少连接信息，请先登录。")
    try:
        txt = base64.b64decode(raw).decode("utf-8")
        c = json.loads(txt)
        if not c.get("db_type"):
            raise ValueError("连接信息缺少字段: db_type")
        if c["db_type"] != "sqlite":
            for k in ("server", "uid"):
                if k not in c or not str(c[k]):
                    raise ValueError(f"连接信息缺少字段: {k}")
        if c.get("pwd"):
            c["pwd"] = maybe_decrypt_pwd(c["pwd"])  # rsa: 前缀 → RSA 解密为明文
        return c
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("连接信息解析失败: " + str(e))

def new_session(ci: dict) -> str:
    """为已解析连接(含明文密码)创建服务端会话，返回 token；密码只存于服务端内存
    惰性清理: 会话数超过阈值时顺带清除过期项, 防长期运行内存泄漏"""
    if len(SESSIONS) > 256:
        now = time.time()
        for tok, item in list(SESSIONS.items()):
            if now - item[1] > SESSION_TTL:
                SESSIONS.pop(tok, None)
    token = secrets.token_hex(16)
    SESSIONS[token] = (dict(ci), time.time())
    return token

def resolve_conn(handler):
    """优先用 X-Session（按名直连的服务端会话，密码不落地前端）；
    否则回退到 X-Conn（手动连接，前端持有明文密码）。会话 12 小时过期。"""
    tok = handler.headers.get("X-Session")
    if tok and tok in SESSIONS:
        item = SESSIONS[tok]
        if time.time() - item[1] > SESSION_TTL:
            SESSIONS.pop(tok, None)
            raise ValueError("会话已过期，请刷新页面重新连接")
        return _norm_db_type(item[0])
    return _norm_db_type(parse_conn_header(handler))

# ------------------------------
# HTTP 处理
# ------------------------------
def _safe_error(e):
    """错误脱敏: 业务校验错误(ValueError)与数据库错误(SQLAlchemyError, 含语法错误/
    表不存在等, 对用户排查 SQL 有直接价值)以及开发模式(DBM_DEV=1)透传详情;
    其余内部异常(代码 bug 等)对外只给通用消息, 防止泄露内部细节。"""
    if isinstance(e, ValueError) or os.environ.get("DBM_DEV"):
        return str(e)
    try:
        from sqlalchemy.exc import SQLAlchemyError
        if isinstance(e, SQLAlchemyError):
            return str(e)
    except Exception:
        pass
    # 脱敏前把原始异常打到结构化日志(控制台 + logs/dbmanager.log), 便于排查
    logger.error("内部错误(已脱敏): %s: %s", type(e).__name__, e, exc_info=True)
    return "服务器内部错误（设置 DBM_DEV=1 可查看详细错误）"


# ------------------------------
# Prometheus 指标: 轻量计数器, /api/metrics 输出; 无第三方依赖
# 指标本体在独立模块 metrics.py(零依赖), 避免 routes 反向 import handler 的循环导入
# ------------------------------
from metrics import METRICS, METRICS_LOCK, record as _metrics_record


def _req_log(method: str):
    """请求日志装饰器: 记录 方法/路径/耗时/状态码/用户(结构化日志) + 指标计数"""
    def deco(fn):
        @functools.wraps(fn)
        def wrap(self, *a, **kw):
            t0 = time.time()
            try:
                r = fn(self, *a, **kw)
                ms = int((time.time() - t0) * 1000)
                status = getattr(self, "_last_status", None) or "-"
                _metrics_record(method, self.path, status if isinstance(status, int) else 200)
                logger.info("%s %s %s %dms user=%s",
                            method, self.path.split("?")[0], status, ms,
                            auth.user_name(self) or "-")
                return r
            except Exception:
                ms = int((time.time() - t0) * 1000)
                _metrics_record(method, self.path, 500)
                logger.error("%s %s 500 %dms user=%s\n%s",
                             method, self.path.split("?")[0], ms,
                             auth.user_name(self) or "-", traceback.format_exc())
                raise
        return wrap
    return deco


# ------------------------------
# 审计日志: 关键操作追加写 logs/audit.log(时间|IP|操作|详情), 超 5MB 轮转
# ------------------------------
AUDIT_DIR = os.path.join(config.BASE_DIR, "logs")
AUDIT_FILE = os.path.join(AUDIT_DIR, "audit.log")
AUDIT_MAX = 5 * 1024 * 1024
_AUDIT_LOCK = threading.Lock()


def _audit(ip, action, detail="", user=""):
    """追加一条审计记录; 任何异常静默忽略(审计不能影响主流程)"""
    try:
        with _AUDIT_LOCK:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            if os.path.exists(AUDIT_FILE) and os.path.getsize(AUDIT_FILE) > AUDIT_MAX:
                os.replace(AUDIT_FILE, AUDIT_FILE + ".1")
            line = "%s | %s | %s | %s | %s\n" % (
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ip, user or "-", action, detail)
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


# 写操作路径(启用账号体系后仅 write 角色可访问)
WRITE_PATHS = {
    "/api/row", "/api/import", "/api/alter", "/api/restore", "/api/sync",
    "/api/routines/save", "/api/routines/drop", "/api/routines/execute",
    "/api/schema-sync", "/api/connections", "/api/connections/delete",
    "/api/transaction/commit", "/api/transaction/rollback",
    "/api/gen-data", "/api/transfer",
}

# 请求体大小上限(五轮评估 P2-2: 防恶意大 POST 体内存耗尽 DoS)
MAX_BODY = 100 * 1024 * 1024


class BodyTooLarge(Exception):
    """请求体超限: 已发送 413 响应, 调用方捕获后直接返回(勿二次响应)"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if os.environ.get("DBM_LOG"):
            try:
                sys.stderr.write("[req] %s %s\n" % (self.command, self.path))
            except Exception:
                pass

    def _request_host(self):
        """解析请求 Host 中的主机名（兼容 [IPv6]:port 形式），返回小写主机名"""
        raw = (self.headers.get("Host") or "").strip()
        if "]" in raw:
            return raw.split("]", 1)[0].lstrip("[").lower()
        if ":" in raw:
            return raw.split(":", 1)[0].strip().lower()
        return raw.lower()

    def _host_allowed(self):
        """防 DNS rebinding：域名形式的 Host 一律拒绝，仅允许 localhost / IP 直连。"""
        host = self._request_host()
        if not host or host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return True
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    def _origin_allowed(self, origin):
        """CORS 白名单：仅允许 回环/内网 IP 来源，或与请求 Host 一致的同源。"""
        try:
            o = urllib.parse.urlparse(origin)
            host = (o.hostname or "").strip().strip("[]").lower()
        except Exception:
            return False
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return True
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True
        except ValueError:
            pass
        req_host = self._request_host()
        return bool(req_host) and host == req_host

    def _send_json(self, code, obj):
        self._last_status = code  # 请求日志用
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for _c in getattr(self, "_extra_cookies", []):
            self.send_header("Set-Cookie", _c)
        origin = self.headers.get("Origin")
        if origin and self._origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Conn, X-Gateway-Token, X-Session, X-User-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()
        try:
            self.wfile.write(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass  # 客户端提前断开, 忽略

    def add_cookie(self, name, value, max_age=43200, http_only=True, same_site="Lax"):
        """设置响应 Set-Cookie(登录会话用): HttpOnly + SameSite=Lax, HTTPS 下加 Secure。
        P1 加固: 账号令牌改 HttpOnly Cookie 承载(防 XSS 窃取), X-User-Token 头仍兼容。"""
        if not hasattr(self, "_extra_cookies"):
            self._extra_cookies = []
        c = "%s=%s; Path=/; Max-Age=%d; SameSite=%s" % (name, value, max_age, same_site)
        if http_only:
            c += "; HttpOnly"
        if _is_https():
            c += "; Secure"
        self._extra_cookies.append(c)

    def _send_html(self, code, html):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        # 基础 CSP: 前端全部外部脚本(CSP 收紧后页面须正常渲染, 已在冒烟验证)
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data: blob:; font-src 'self' data:; "
                         "connect-src 'self' ws: wss:; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        if n > MAX_BODY:   # P2-2: 请求体硬上限, 防内存耗尽 DoS
            self._send_json(413, {"error": "请求体超过大小上限(%dMB)" % (MAX_BODY // 1048576)})
            raise BodyTooLarge
        raw = self.rfile.read(n).decode("utf-8")
        if os.environ.get("DBM_LOG"):
            try:
                sys.stderr.write("[body] %s\n" % raw[:400])
            except Exception:
                pass
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj.get("pwd"):
            obj["pwd"] = maybe_decrypt_pwd(obj["pwd"])  # rsa: 前缀 → RSA 解密为明文
        return obj

    def _parse(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        return p.path, q

    def do_OPTIONS(self):
        if not self._host_allowed():
            self._send_json(403, {"error": "非法 Host（仅支持 IP 直连访问）"})
            return
        self._send_json(200, {})

    def _gateway_blocked(self):
        """外部(公网)且未通过网关验证 -> 拦截并返回 True。"""
        if _gateway_allowed(self):
            return False
        path, _ = self._parse()
        if path in ("/", "/index.html"):
            return False  # 允许加载 UI 外壳，由前端 /api/config 触发验证弹窗
        # 静态资源与前端入口(UI 外壳, 不含业务数据) + 网关状态查询: 放行以渲染验证弹窗
        if path.startswith("/v2"):
            return False
        for _prefix in STATIC_DIRS:
            if path.startswith(_prefix):
                return False
        if path.startswith("/api/gateway/"):
            return False
        if path in ("/api/config", "/api/pubkey"):
            return False  # 前端依赖其判断是否弹网关验证
        self._send_json(401, {"error": "需要公网访问验证", "require_gateway": True})
        return True

    def _auth_blocked(self):
        """账号体系启用时, 未登录的 API 请求 -> 拦截并返回 True(静态资源/首页/登录相关放行)"""
        if not auth.auth_enabled():
            return False
        path, _ = self._parse()
        if path in ("/", "/index.html"):
            return False
        # 静态资源与前端入口(登录页外壳, 不含业务数据): 未登录必须可加载, 否则登录 UI 无法渲染
        if path.startswith("/v2"):
            return False
        for _prefix in STATIC_DIRS:
            if path.startswith(_prefix):
                return False
        if path in ("/api/config", "/api/pubkey", "/api/login", "/api/register", "/api/logout",
                    "/api/gateway/login", "/api/gateway/status",
                    "/api/health", "/api/metrics"):
            return False
        if auth.current_user(self):
            return False
        self._send_json(401, {"error": "请先登录", "require_login": True})
        return True

    def _must_change_blocked(self):
        """强制首次改密: 默认账号未改密前, 业务 API 一律 403,
        仅放行 改密/登出/配置查询 等必要通道(否则改密流程无法进行)。
        开发模式(DBM_DEV=1)跳过——假 admin 会话无真实改密流程。"""
        if not auth.auth_enabled() or os.environ.get("DBM_DEV") == "1":
            return False
        path, _ = self._parse()
        if path in ("/api/password", "/api/logout", "/api/config", "/api/pubkey",
                    "/api/login", "/api/gateway/login", "/api/gateway/status",
                    "/api/health", "/api/metrics"):
            return False
        u = auth.current_user(self)
        if not u or not auth.must_change_pwd(u["user"]):
            return False
        self._send_json(403, {"error": "首次登录请先修改默认密码", "must_change_pwd": True})
        return True

    def _require_write(self):
        """写操作权限: 未启用账号体系直接放行; 启用后仅 write/admin 角色可执行"""
        if not auth.auth_enabled():
            return True
        u = auth.current_user(self)
        if u and u["role"] in ("write", "admin"):
            return True
        self._send_json(403, {"error": "只读账号无权执行写操作"})
        return False

    def _require_admin(self):
        """管理操作权限(连接可见性/只读标记/账号管理): 仅 admin 可执行"""
        if not auth.auth_enabled():
            return True
        u = auth.current_user(self)
        if u and u["role"] == "admin":
            return True
        self._send_json(403, {"error": "该操作仅管理员可执行"})
        return False

    def _visible_connections(self):
        """按当前用户过滤连接可见性: admin 看全部; 普通用户只看公开连接(visible_to 为空)与自己可见的连接。
        未启用账号体系时不过滤(单用户自用全部可见)。"""
        conns = list_connections()
        if not auth.auth_enabled():
            return conns
        u = auth.current_user(self)
        if u and u["role"] == "admin":
            return conns
        name = (u or {}).get("user", "")
        return [c for c in conns
                if not c.get("visible_to") or name in c.get("visible_to")]

    def _conn_readonly_blocked(self):
        """连接带 read_only 标记时拒绝写操作: 返回 True 表示已拦截(需连接的写接口统一调用)。
        连接管理接口(保存/删除连接)不适用——它们是管理操作而非数据写操作。"""
        try:
            path, _ = self._parse()
            if path in ("/api/connections", "/api/connections/delete"):
                return False
            conn = resolve_conn(self)
            if conn.get("mode") == "read_only":
                self._send_json(403, {"error": "该连接已标记为只读(生产库保护), 禁止写操作"})
                return True
        except Exception:
            pass  # 无连接的写接口(如连接管理)不适用, 跳过
        return False

    def _audit_action(self, action, detail=""):
        """审计并自动附带当前登录用户(未登录/未启用账号体系记 -)"""
        _audit(self.client_address[0], action, detail, auth.user_name(self))

    def _do_gateway_login(self):
        b = self._body()
        tok = b.get("token", "") if isinstance(b, dict) else ""
        ip = self.client_address[0]
        now = time.time()
        # 限流: 连续失败达阈值则锁定 5 分钟, 防暴力破解
        f = GATEWAY_FAIL.get(ip)
        if f and f[0] >= GATEWAY_MAX_FAIL and now - f[1] < GATEWAY_LOCK_SEC:
            self._send_json(429, {"ok": False, "error": "尝试次数过多, 请 5 分钟后再试"})
            return
        if hashlib.sha256(tok.encode("utf-8")).hexdigest() == GATEWAY_HASH:
            GATEWAY_FAIL.pop(ip, None)
            st = secrets.token_hex(16)  # 随机会话 id, cookie 不再存持久哈希
            GATEWAY_SESSIONS[st] = now + GATEWAY_SESSION_TTL
            cookie = ("dbm_gw=%s; Path=/; HttpOnly; Max-Age=28800; SameSite=Lax"
                      % st)
            if _is_https():
                cookie += "; Secure"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", cookie)
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            if origin and self._origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Gateway-Token, X-User-Token")
            self.end_headers()
            host_hdr = self.headers.get("Host") or f"{HOST}:{PORT}"
            self.wfile.write(json.dumps({"ok": True,
                                         "api_base": _scheme() + "://" + host_hdr}).encode("utf-8"))
        else:
            cnt, ts = f if f else (0, now)
            GATEWAY_FAIL[ip] = [cnt + 1, ts if cnt else now]
            if len(GATEWAY_FAIL) > 1000:  # 防字典无限增长
                GATEWAY_FAIL.clear()
            self._send_json(401, {"ok": False, "error": "访问令牌错误"})

    @_req_log("GET")
    def do_GET(self):
        path, q = self._parse()
        try:
            if not self._host_allowed():
                self._send_json(403, {"error": "非法 Host（仅支持 IP 直连访问）"})
                return
            if self._gateway_blocked():
                return
            if self._auth_blocked():
                return
            if self._must_change_blocked():
                return
            # 静态资源(css/js): 仅白名单子目录下的扁平文件, 防目录穿越
            for prefix, (subdir, ctype) in STATIC_DIRS.items():
                if path.startswith(prefix):
                    rel = path[len(prefix):]
                    if rel and ".." not in rel and "/" not in rel and "\\" not in rel:
                        fpath = os.path.join(config.BASE_DIR, subdir, rel)
                        if os.path.isfile(fpath):
                            with open(fpath, "rb") as _f:
                                data = _f.read()
                            self.send_response(200)
                            self.send_header("Content-Type", ctype)
                            self.send_header("Cache-Control", "no-store")
                            self.send_header("X-Content-Type-Options", "nosniff")
                            self.send_header("Content-Length", str(len(data)))
                            self.end_headers()
                            self.wfile.write(data)
                            return
            if path in ("/", "/index.html"):
                try:
                    # 前端收口: 默认入口指向 Vue3 构建产物(frontend/dist);
                    # dist 缺失时回退旧版 index.html(开发环境未构建的兜底, 不白屏)
                    if os.path.exists(config.VUE_INDEX_FILE):
                        with open(config.VUE_INDEX_FILE, "r", encoding="utf-8") as _f:
                            self._send_html(200, _f.read())
                    else:
                        with open(config.INDEX_FILE, "r", encoding="utf-8") as _f:
                            self._send_html(200, _f.read())
                except FileNotFoundError:
                    self._send_html(404, "index.html not found")
                return
            # /v2 保留兼容(迁移期入口); / 已优先 Vue3, 旧前端 js/ 目录保留供回退
            if path in ("/v2", "/v2/", "/v2/index.html"):
                try:
                    with open(config.VUE_INDEX_FILE, "r", encoding="utf-8") as _f:
                        self._send_html(200, _f.read())
                except FileNotFoundError:
                    self._send_html(404, "v2 index.html not found (先构建 frontend: npm run build)")
                return
            # Vue3 迁移版静态资源: /assets/ 与 /v2/assets/ 均从 frontend/dist/assets/ 读
            # (base='./' 相对路径在 /v2 页解析为 /assets/; 直接访问 /v2/assets/ 也兼容)
            for _prefix in ("/assets/", "/v2/assets/"):
                if path.startswith(_prefix):
                    rel = path[len(_prefix):]
                    # 仅扁平哈希文件(拒 .. / 子目录), 与旧前端白名单同等安全策略
                    if rel and ".." not in rel and "/" not in rel and "\\" not in rel:
                        fpath = os.path.join(config.VUE_DIST_DIR, "assets", rel)
                        if os.path.isfile(fpath):
                            ctype = ("text/css; charset=utf-8" if rel.endswith(".css")
                                     else "application/javascript; charset=utf-8")
                            with open(fpath, "rb") as _f:
                                data = _f.read()
                            self.send_response(200)
                            self.send_header("Content-Type", ctype)
                            self.send_header("Cache-Control", "no-store")
                            self.send_header("X-Content-Type-Options", "nosniff")
                            self.send_header("Content-Length", str(len(data)))
                            self.end_headers()
                            self.wfile.write(data)
                            return
            for _mod in ROUTE_MODS:
                if _mod.handle_get(self, path, q):
                    return
            self._send_json(404, {"error": "not found"})
        except BodyTooLarge:
            return  # 413 已在 _body 发送
        except Exception as e:
            self._send_json(500, {"error": _safe_error(e)})

    @_req_log("POST")
    def do_POST(self):
        path, q = self._parse()
        try:
            if not self._host_allowed():
                self._send_json(403, {"error": "非法 Host（仅支持 IP 直连访问）"})
                return
            if self._gateway_blocked():
                return
            if self._auth_blocked():
                return
            if self._must_change_blocked():
                return
            # 写操作网关(与 do_PUT/do_DELETE 对齐): 角色 + 连接只读双校验, 防 read 越权写
            if path in WRITE_PATHS and not self._require_write():
                return
            if path in WRITE_PATHS and self._conn_readonly_blocked():
                return
            for _mod in ROUTE_MODS:
                if _mod.handle_post(self, path, q):
                    return
            self._send_json(404, {"error": "not found"})
        except BodyTooLarge:
            return  # 413 已在 _body 发送
        except Exception as e:
            self._send_json(500, {"error": _safe_error(e)})

    @_req_log("PUT")
    def do_PUT(self):
        path, q = self._parse()
        try:
            if not self._host_allowed():
                self._send_json(403, {"error": "非法 Host（仅支持 IP 直连访问）"})
                return
            if self._gateway_blocked():
                return
            if self._auth_blocked():
                return
            if self._must_change_blocked():
                return
            if path in WRITE_PATHS and not self._require_write():
                return
            if path in WRITE_PATHS and self._conn_readonly_blocked():
                return
            if path == "/api/row":
                conn = resolve_conn(self)
                b = self._body()
                use_tx = b.get("transaction", False)
                d = mutate(conn, "PUT", b["s"], b["t"], b, use_tx, b.get("tx_id", ""))
                self._send_json(200, d)
                self._audit_action( "row_update", "%s.%s" % (b["s"], b["t"]))
                return
            self._send_json(404, {"error": "not found"})
        except BodyTooLarge:
            return  # 413 已在 _body 发送
        except Exception as e:
            self._send_json(500, {"error": _safe_error(e)})

    # ---- 包装方法(routes 模块经 handler 实例调用, 避免循环导入) ----
    def _resolve_conn(self):
        return resolve_conn(self)

    def _new_session(self, ci):
        return new_session(ci)

    def _scheme(self):
        return _scheme()

    def _discover_navicat_connections(self):
        return discover_navicat_connections()

    def _get_default_conn(self):
        return get_default_conn()

    def _gateway_allowed(self):
        return _gateway_allowed(self)

    @_req_log("DELETE")
    def do_DELETE(self):
        path, q = self._parse()
        try:
            if not self._host_allowed():
                self._send_json(403, {"error": "非法 Host（仅支持 IP 直连访问）"})
                return
            if self._gateway_blocked():
                return
            if self._auth_blocked():
                return
            if self._must_change_blocked():
                return
            if path in WRITE_PATHS and not self._require_write():
                return
            if path in WRITE_PATHS and self._conn_readonly_blocked():
                return
            if path == "/api/row":
                conn = resolve_conn(self)
                b = self._body()
                use_tx = b.get("transaction", False)
                d = mutate(conn, "DELETE", b["s"], b["t"], b, use_tx, b.get("tx_id", ""))
                self._send_json(200, d)
                self._audit_action( "row_delete", "%s.%s" % (b["s"], b["t"]))
                return
            self._send_json(404, {"error": "not found"})
        except BodyTooLarge:
            return  # 413 已在 _body 发送
        except Exception as e:
            self._send_json(500, {"error": _safe_error(e)})

# ------------------------------
# 前端页面
# ------------------------------
# 默认连接（来自环境变量 DBM_DEFAULT_CONN，JSON 字符串；含密码，仅本进程内存，不落盘）

# ------------------------------
# 公网访问网关验证（仅对“外部/公网”客户端生效；内网/回环免验证）
# - 网关令牌优先级：环境变量 DBM_GATEWAY_TOKEN > 已保存的 .dbm_gateway > 启动时随机生成（落地 .dbm_gateway，权限 600）
# - 外部客户端必须携带网关令牌（Cookie: dbm_gw 或请求头 X-Gateway-Token）方可访问任何 API
# - 内网（RFC1918 / 回环 / 链路本地 / IPv6 ULA）客户端无需额外验证，保持局域网免密
# ------------------------------
GATEWAY_TOKEN_FILE = os.path.join(config.BASE_DIR, ".dbm_gateway")

def _load_gateway_token():
    env = os.environ.get("DBM_GATEWAY_TOKEN")
    if env:
        return env
    tf = GATEWAY_TOKEN_FILE
    if os.path.exists(tf):
        try:
            t = open(tf, "r", encoding="utf-8").read().strip()
            if t:
                return t
        except Exception:
            pass
    t = secrets.token_urlsafe(24)
    try:
        with open(tf, "w", encoding="utf-8") as _f:
            _f.write(t)
        try:
            os.chmod(tf, 0o600)
        except Exception:
            pass
        logger.warning("=" * 64)
        logger.warning("⚠ 已自动生成公网访问网关令牌（请妥善保存，重启后不变；")
        logger.warning("  也可设置环境变量 DBM_GATEWAY_TOKEN 固定令牌）：")
        logger.warning("   " + t)
        logger.warning("=" * 64)
    except Exception:
        pass
    sys.stdout.flush()
    return t

GATEWAY_TOKEN = _load_gateway_token()
GATEWAY_HASH = hashlib.sha256(GATEWAY_TOKEN.encode("utf-8")).hexdigest()

# 网关会话(登录成功签发随机 token, cookie 只存会话 id, 不存哈希本身, 可单独吊销)
GATEWAY_SESSIONS = {}       # token -> 过期时间戳
GATEWAY_SESSION_TTL = 8 * 3600
# 登录限流: 按客户端 IP 计数, 连续失败超阈值锁定, 防暴力破解
GATEWAY_FAIL = {}           # IP -> [连续失败次数, 首次失败时间戳]
GATEWAY_MAX_FAIL = 5        # 连续失败 5 次
GATEWAY_LOCK_SEC = 300      # 锁定 5 分钟

# ------------------------------
# HTTPS / SSL（公网强烈建议开启；自签名证书可自动生成，亦支持自带证书）
# - 显式证书：设置环境变量 DBM_SSL_CERT / DBM_SSL_KEY
# - 一键自签名：设置 DBM_SSL=1 即自动生成自签名证书(.dbm_cert.pem/.dbm_key_ssl.pem)并启用
# - 启用后 ipaddress 判定、Cookie 的 Secure 标记、api_base 的 https 协议均自动联动
# ------------------------------
SSL_CERT = None
SSL_KEY = None
USE_HTTPS = False

def _gen_self_signed_cert(cert_path, key_path):
    """生成自签名证书（覆盖 localhost / 127.0.0.1 / ::1 / 本机可达 IP），有效期 825 天。"""
    sans = ["DNS:localhost", "IP:127.0.0.1", "IP:::1"]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ip.startswith("127.") or ip == "::1":
                continue
            sans.append("IP:" + ip)
    except Exception:
        pass
    san = ",".join(sorted(set(sans)))
    openssl = shutil.which("openssl") or "openssl"
    cmd = [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
           "-keyout", key_path, "-out", cert_path, "-days", "825",
           "-subj", "/CN=DBManager.local", "-addext", "subjectAltName=" + san]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        # openssl 不可用时回退 cryptography（需 pip install cryptography）
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            sub = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DBManager.local")])
            sans_list = [x509.DNSName("localhost"),
                         x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                         x509.IPAddress(ipaddress.ip_address("::1"))]
            cert = (x509.CertificateBuilder().subject_name(sub).issuer_name(sub)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
                    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=825))
                    .add_extension(x509.SubjectAlternativeName(sans_list), critical=False)
                    .sign(key, hashes.SHA256()))
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(serialization.Encoding.PEM,
                                          serialization.NoEncryption()))
        except Exception:
            raise RuntimeError("生成自签名证书失败：openssl 不可用且未安装 cryptography")
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass

def _ssl_setup():
    """解析 SSL 证书来源并设置全局 USE_HTTPS / SSL_CERT / SSL_KEY。"""
    global SSL_CERT, SSL_KEY, USE_HTTPS
    cert = os.environ.get("DBM_SSL_CERT")
    key = os.environ.get("DBM_SSL_KEY")
    if cert and key:
        SSL_CERT, SSL_KEY, USE_HTTPS = cert, key, True
        return
    dcert = os.path.join(config.BASE_DIR, ".dbm_cert.pem")
    dkey = os.path.join(config.BASE_DIR, ".dbm_key_ssl.pem")
    # DBM_SSL=1 或已存在默认自签名证书时启用
    if os.environ.get("DBM_SSL") == "1" or os.path.exists(dcert):
        if not (os.path.exists(dcert) and os.path.exists(dkey)):
            try:
                _gen_self_signed_cert(dcert, dkey)
            except Exception as e:
                logger.error("自签名证书生成失败：%s", e)
                sys.stdout.flush()
                return
        SSL_CERT, SSL_KEY, USE_HTTPS = dcert, dkey, True

def _is_https():
    return USE_HTTPS

def _scheme():
    return "https" if _is_https() else "http"

def _client_is_internal(handler):
    """根据客户端源地址判断是否为内网/回环（免网关验证）。"""
    raw = handler.client_address[0]
    try:
        ip = ipaddress.ip_address(raw)
    except Exception:
        return False
    if ip.version == 6 and getattr(ip, "ipv4_mapped", None) is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_private or ip.is_link_local

def _gateway_cookie_ok(handler):
    cookie = handler.headers.get("Cookie", "")
    now = time.time()
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("dbm_gw="):
            val = part[len("dbm_gw="):]
            if val and val in GATEWAY_SESSIONS:
                if GATEWAY_SESSIONS[val] > now:
                    return True
                GATEWAY_SESSIONS.pop(val, None)  # 过期会话顺带清理
    if len(GATEWAY_SESSIONS) > 5000:  # 防字典无限增长
        for k, exp in list(GATEWAY_SESSIONS.items()):
            if exp <= now:
                GATEWAY_SESSIONS.pop(k, None)
    tok = handler.headers.get("X-Gateway-Token")
    if tok and hashlib.sha256(tok.encode("utf-8")).hexdigest() == GATEWAY_HASH:
        return True
    return False

def _gateway_allowed(handler):
    if _client_is_internal(handler):
        return True
    return _gateway_cookie_ok(handler)

def get_default_conn():
    raw = os.environ.get("DBM_DEFAULT_CONN")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None
    # 未配置：优先选本机(localhost)的 Navicat 连接作为默认，便于开箱即用
    for c in discover_navicat_connections():
        h = (c.get("server") or "").lower()
        if h in ("localhost", "127.0.0.1", "."):
            c2 = dict(c)
            c2.pop("name", None)
            c2.pop("databases", None)
            return c2
    return None


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


