# -*- coding: utf-8 -*-
"""dbmanager - routes.connection: 连接: 测试/建立会话/库列表/保存连接/注册/改密/公钥/配置"""


from core import auth
from core import config
from core.error import safe_error

from core.config import DEFAULT_PORT, HOST, PORT
from core.crypto import rsa_public_pem
from db.dbcore import (
    test_connection, is_safe_server, _safe_sqlite_path,
)
from ops import (
    get_databases, get_tables,
)
from db.store import (
    delete_connection, get_connection_by_name, save_connection,
)


def handle_get(handler, path, q):
    """GET 路由: 已处理返回 True, 否则 False"""
    if path == "/api/config":
                    host_hdr = handler.headers.get("Host") or f"{HOST}:{PORT}"
                    api_base = handler._scheme() + "://" + host_hdr
                    if handler._gateway_allowed():
                        u = auth.current_user(handler)
                        handler._send_json(200, {"default_conn": handler._get_default_conn(),
                                              "connections": handler._discover_navicat_connections(),
                                              "saved_connections": handler._visible_connections(),
                                              "api_base": api_base,
                                              "version": config.VERSION,
                                              "auth_required": auth.auth_enabled(),
                                              "auth_user": u["user"] if u else None,
                                              "auth_role": u["role"] if u else None,
                                              "must_change_pwd": auth.must_change_pwd(u["user"]) if u else False,
                                              "register_enabled": auth.register_enabled(),
                                              "gateway_required": False})
                    else:
                        handler._send_json(401, {"api_base": api_base,
                                              "gateway_required": True,
                                              "require_gateway": True,
                                              "error": "需要公网访问验证"})
                    return True
    if path == "/api/pubkey":
                    # 传输层 RSA 公钥(前端用于加密密码; 公钥公开, 私钥仅服务端持有)
                    handler._send_json(200, {"pubkey": rsa_public_pem()})
                    return True
    if path == "/api/connections":
                    handler._send_json(200, handler._visible_connections())
                    return True
    return False

def handle_post(handler, path, q):
    """POST 路由: 已处理返回 True, 否则 False"""
    if path == "/api/register":
                    # 内网默认关闭自助注册(账号由管理员创建), DBM_ALLOW_REGISTER=1 开启
                    if not auth.register_enabled():
                        handler._send_json(403, {"error": "自助注册已关闭, 请联系管理员创建账号"})
                        return True
                    b = handler._body()
                    if not isinstance(b, dict):
                        handler._send_json(400, {"error": "参数错误"})
                        return True
                    ok, msg = auth.register(b.get("username", ""), b.get("password", ""),
                                            handler.client_address[0])
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg})
                        handler._audit_action("register", b.get("username", ""))
                    else:
                        handler._send_json(400, {"error": msg})
                    return True
    if path == "/api/password":
                    if handler._auth_blocked():
                        return True
                    b = handler._body()
                    u = auth.current_user(handler)
                    if not u:
                        handler._send_json(401, {"error": "请先登录", "require_login": True})
                        return True
                    ok, msg = auth.change_password(u["user"],
                                                   b.get("old_password") or b.get("old_pwd", ""),
                                                   b.get("new_password") or b.get("new_pwd", ""))
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg})
                        handler._audit_action("change_password", u["user"])
                    else:
                        handler._send_json(400, {"error": msg})
                    return True
    if path == "/api/test":
                    # SSRF 缓解: 连接测试属管理操作, 需 write 以上角色; server 仅允许主机/IP:端口
                    if not handler._require_write():
                        return True
                    b = handler._body()
                    if b.get("name"):
                        c = get_connection_by_name(b["name"])
                        if not c:
                            handler._send_json(404, {"error": f"未找到连接: {b['name']}"})
                            return True
                        b = c
                    srv = str(b.get("server") or "")
                    if srv and not is_safe_server(srv):
                        handler._send_json(400, {"error": "server 仅支持主机名或 IP(禁止 URL/路径形式及云元数据/链路本地地址)"})
                        return True
                    try:
                        test_connection(b)
                        server = b.get("server") or "localhost"
                        port = b.get("port") or DEFAULT_PORT.get(b.get("db_type", "mysql"), "")
                        handler._send_json(200, {"ok": True, "message": f"连接成功 ({server}:{port})"})
                    except Exception as e:
                        # 统一脱敏 + 正确状态码(500): 业务/DB 错误透传, 内部异常脱敏
                        handler._send_json(500, {"ok": False, "error": safe_error(e)})
                    return True
    if path == "/api/connect":
                    b = handler._body()
                    is_named = bool(b.get("name"))
                    # --- SSRF 缓解 + 角色门禁(P0-3) ---
                    # 手动连接(无 name, 任意 server)属网络探测, 需 write 以上角色;
                    # server 必须为合法主机/IP(禁 URL/路径/云元数据/链路本地地址)。
                    # 命名连接沿用其保存的 server(可信), 仅做细粒度 ACL 校验。
                    if not is_named:
                        if not handler._require_write():
                            return True
                        srv = str(b.get("server") or "")
                        if srv and not is_safe_server(srv):
                            handler._send_json(400, {"error": "server 仅支持主机名或 IP(禁止 URL/路径形式及云元数据/链路本地地址)"})
                            return True
                    # SQLite 数据库路径沙箱(防 ../../ 逃逸读取系统文件)
                    if (b.get("db_type") or "").lower() == "sqlite":
                        dbp = str(b.get("database") or "").strip()
                        if dbp and dbp != ":memory:":
                            try:
                                _safe_sqlite_path(dbp)
                            except ValueError as e:
                                handler._send_json(400, {"error": str(e)})
                                return True
                    if is_named:
                        c = get_connection_by_name(b["name"])
                        if not c:
                            handler._send_json(404, {"error": f"未找到连接: {b['name']}"})
                            return True
                        # 命名连接入口权限校验(细粒度 ACL): 未配置权限的用户不受限(兼容老部署);
                        # admin 始终放行。手动连接(无 name)已走上方 write 门禁, 不受连接级限制。
                        u = auth.current_user(handler)
                        if u and u["role"] != "admin" and not auth.can_access(
                                u["user"], u["role"], b["name"], "read"):
                            handler._send_json(403, {"error": "无权访问该连接(%s)" % b["name"],
                                                      "perm_denied": True})
                            return True
                        # 按名直连允许覆盖字段(如跨库切换 database): 保留保存连接的解密密码, 应用 body 覆盖
                        for k, v in b.items():
                            if k != "name":
                                c[k] = v
                        b = c
                    token = handler._new_session(b)
                    meta = {k: b.get(k) for k in ("name", "db_type", "server", "port", "database", "uid")}
                    tables = get_tables(b)
                    resp = {"ok": True, "tables": tables, "session": token, "connection": meta}
                    handler._send_json(200, resp)
                    handler._audit_action( "connect",
                           "%s %s@%s/%s" % (meta.get("db_type", ""), meta.get("uid", ""),
                                            meta.get("server", ""), meta.get("database", "")))
                    return True
    if path == "/api/connections":
                    b = handler._body()
                    # 内网 ACL: 设置可见性/只读标记属管理操作, 仅 admin
                    if (isinstance(b, dict) and (b.get("visible_to") or b.get("mode")) and
                            not handler._require_admin()):
                        return True
                    # 归属校验(P1-7): 记录创建者; 非 admin 修改他人创建的连接时拒绝
                    if isinstance(b, dict):
                        u = auth.current_user(handler)
                        uname = (u or {}).get("user", "")
                        if auth.auth_enabled() and uname and u["role"] != "admin":
                            existing = None
                            try:
                                existing = get_connection_by_name(b.get("name") or "")
                            except Exception:
                                existing = None
                            if existing and existing.get("owner") and existing["owner"] != uname:
                                handler._send_json(403, {"error": "仅连接创建者或管理员可修改该连接"})
                                return True
                            b["owner"] = uname
                    rec = save_connection(b)
                    rec.pop("pwd_enc", None)
                    handler._send_json(200, {"ok": True, "connection": rec})
                    handler._audit_action( "save_connection",
                           "%s %s" % (rec.get("db_type", ""), rec.get("name", "")))
                    return True
    if path == "/api/connections/delete":
                    b = handler._body()
                    name = b.get("name") or ""
                    # 归属校验(P1-7): 非 admin 仅能删除自己创建的连接(老连接无 owner 视为公共, 保持兼容)
                    u = auth.current_user(handler)
                    uname = (u or {}).get("user", "")
                    if auth.auth_enabled() and uname and u["role"] != "admin":
                        existing = None
                        try:
                            existing = get_connection_by_name(name)
                        except Exception:
                            existing = None
                        if existing and existing.get("owner") and existing["owner"] != uname:
                            handler._send_json(403, {"error": "仅连接创建者或管理员可删除该连接"})
                            return True
                    delete_connection(name)
                    handler._send_json(200, {"ok": True})
                    return True
    if path == "/api/databases":
                    b = handler._body()
                    if b.get("db_type"):
                        conn = b  # 兼容旧调用: body 直接传连接
                    else:
                        conn = handler._resolve_conn()  # 会话模式: 连接内列库, 无需再传密码
                    handler._send_json(200, get_databases(conn))
                    return True
    if path == "/api/conn/tables":
                    # 权限配置辅助: 管理员拉取某保存连接的真实表名列表(仅 admin, 不建立会话)
                    if not handler._require_admin():
                        return True
                    b = handler._body()
                    c = get_connection_by_name((b or {}).get("name", ""))
                    if not c:
                        handler._send_json(404, {"error": "未找到连接"})
                        return True
                    try:
                        tables = get_tables(c)
                        names = [t.get("name") if isinstance(t, dict) else str(t) for t in tables]
                        handler._send_json(200, {"tables": names})
                    except Exception as e:
                        # 统一脱敏 + 正确状态码(500)
                        handler._send_json(500, {"ok": False, "error": safe_error(e)})
                    return True
    return False
