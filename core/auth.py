# -*- coding: utf-8 -*-
"""dbmanager 账号体系（最小商用改造 + 内网分治）：
- 账号存 users.json（pbkdf2 密码哈希 + 角色 read/write/admin）
- 注意: 启动时 ensure_default() 会**自动创建** users.json + 默认账号 admin/admin123(admin 角色)
  → 默认部署即"认证开启 + 弱口令", 请务必立即改密(可用 DBM_DEFAULT_PWD 覆盖首次建库密码)
- /api/login 换取 X-User-Token 会话；写操作要求 write 角色，管理操作要求 admin 角色
- 启用方式：users.json 存在(ensure_default 自动建)或设置环境变量 DBM_AUTH=1
- 内网 LDAP/AD 接入：设置 DBM_LDAP_URL + DBM_LDAP_BASE 启用（ldap3 库，未安装自动降级）；LDAP 认证通过的用户按 users.json 配角色，未配置默认 read
- 自助注册：默认关闭（内网合规），DBM_ALLOW_REGISTER=1 开启
"""

import hashlib
import os
import re
import secrets
import threading
import time

from core.config import BASE_DIR, conf
from core.i18n import t  # 轻量 i18n: 用户可见文案走 t("key"), 默认 zh_CN 行为不变
from db import sqlitedb  # 用户/权限数据存 SQLite(dbmanager.db); 旧 users.json 首次启动自动迁移

USERS_FILE = os.path.join(BASE_DIR, "users.json")  # 遗留路径: 仅用于迁移检测与老部署兼容
USER_SESSIONS = {}  # token -> {user, role, exp, login_time, ip, last_active}
SESSION_TTL = 12 * 3600  # 登录会话 12 小时
USER_ACTIVITY = {}  # 用户 -> {path: 最后操作路径, _t: 记录时间}(在线管理面板"当前操作", 节流写入)
_LOCK = threading.Lock()

# 登录限流: 同一 IP+用户名 连续失败 MAX_FAIL 次锁定 LOCK_SEC 秒
LOGIN_FAIL = {}
LOGIN_MAX_FAIL = 5
LOGIN_LOCK_SEC = 300

# 首次启用时的默认账号（管理员）——密码 admin123, 首次登录后请手工改 users.json
# 可用 DBM_DEFAULT_PWD(或 dbmanager.conf [auth] default_pwd) 覆盖首次创建的默认密码(仅首次建库生效, 之后修改请走改密接口)
DEFAULT_USER = "admin"
DEFAULT_PWD = conf("DBM_DEFAULT_PWD") or "admin123"

# LDAP/AD 接入（内网可选）: 配置后 LDAP 用户可直接登录, users.json 管理角色与本地管理员
# 注意: 以下为 import 时的快照(兼容旧代码引用); 运行时判定一律走 _ldap_cfg() 动态读取,
# 使 dbmanager.conf 修改(如管理界面改 LDAP 项)无需重启即可生效。
LDAP_URL = conf("DBM_LDAP_URL")  # 如 ldap://192.168.1.10:389
LDAP_BASE = conf("DBM_LDAP_BASE")  # 如 dc=company,dc=com
LDAP_BINDDN = conf("DBM_LDAP_BINDDN")  # 可选: 绑定查询账号(有则先按用户名查 DN)
LDAP_BINDPW = conf("DBM_LDAP_BINDPW")
LDAP_ATTR = conf("DBM_LDAP_ATTR") or "sAMAccountName"  # 用户名属性(AD 默认, OpenLDAP 常用 uid)


def _ldap_cfg():
    """运行时读取 LDAP 配置(配置管理界面修改后即时生效, 无需重启)"""
    return {
        "url": conf("DBM_LDAP_URL"),
        "base": conf("DBM_LDAP_BASE"),
        "binddn": conf("DBM_LDAP_BINDDN"),
        "bindpw": conf("DBM_LDAP_BINDPW"),
        "attr": conf("DBM_LDAP_ATTR") or "sAMAccountName",
    }


def ldap_enabled():
    """LDAP 接入是否启用(需 URL + BASE)"""
    c = _ldap_cfg()
    return bool(c["url"] and c["base"])


def register_enabled():
    """自助注册开关: 局域网一次性部署定位, 默认开启(成员自助注册, 管理员审批后可用);
    显式 DBM_ALLOW_REGISTER=0(或 dbmanager.conf [auth] allow_register=0) 可关闭(公网/合规场景)"""
    return conf("DBM_ALLOW_REGISTER") != "0"


def auth_enabled():
    """启用条件：SQLite 已有用户 或 users.json 存在(迁移前) 或 DBM_AUTH=1(或 dbmanager.conf [auth] auth_enabled=1)。
    默认部署 ensure_default() 会在 SQLite 创建默认账号 -> 默认即启用认证(默认口令 admin123)。
    顺带执行幂等迁移: 默认 admin 账号角色升级为 admin(内网管理权限)。"""
    _migrate_admin_role()
    if conf("DBM_AUTH") == "1":
        return True
    if sqlitedb.has_users():
        return True
    return os.path.exists(USERS_FILE)  # 老部署迁移前兜底


def _migrate_admin_role():
    """幂等迁移: users.json 中默认 admin 账号若仍是 write 角色, 升级为 admin。
    首次引入 admin 角色后的一次性数据升级, 之后不再改动。"""
    if not os.path.exists(USERS_FILE):
        return
    try:
        users = _load_users()
        if users.get(DEFAULT_USER, {}).get("role") != "admin":
            users[DEFAULT_USER] = dict(users[DEFAULT_USER], role="admin")
            _save(users)
    except Exception:
        pass


def ensure_default():
    """SQLite 无用户时创建默认管理员账号(首次部署自动生成, 调用方应据此提示改密)
    旧 users.json 部署: 存在则先迁移到 SQLite(数据入库后 json 改名 .bak)。
    返回 True=本次新建默认账号(需提示改密), False=已有部署(仅平滑迁移 admin 角色)。"""
    # 老部署迁移: users.json 存在 -> 导入 SQLite(仅当 SQLite 空)
    if os.path.exists(USERS_FILE):
        sqlitedb.migrate_users_json(USERS_FILE)
    if sqlitedb.has_users():
        # 平滑迁移: 默认 admin 账号若仍是 write 角色, 自动升级为 admin(管理员应具备管理权限)
        try:
            users = _load_users()
            if users.get(DEFAULT_USER, {}).get("role") != "admin":
                users[DEFAULT_USER] = dict(users[DEFAULT_USER], role="admin")
                _save(users)
        except Exception:
            pass
        return False
    try:
        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac("sha256", DEFAULT_PWD.encode(), bytes.fromhex(salt), 120000).hex()
        # is_default: 默认账号标记(强制首改密依据), 改密成功后清除
        _save({DEFAULT_USER: {"pwd_hash": h, "salt": salt, "role": "admin", "is_default": True}})
        return True
    except Exception:
        return False


def is_default_pwd():
    """admin 账号是否仍使用默认口令(admin123 或 DBM_DEFAULT_PWD)——用于启动时提示改密"""
    try:
        users = _load_users()
        a = users.get(DEFAULT_USER)
        if not a:
            return False
        return _hash(DEFAULT_PWD, a.get("salt", "")) == a.get("pwd_hash", "")
    except Exception:
        return False


def must_change_pwd(username):
    """该用户是否须强制改密: 新建的默认账号(is_default 标记) 或
    密码仍等于默认口令(兼容老部署 users.json 无标记但还挂着默认口令的情况)。
    改密成功/管理员重置密码后自动解除。"""
    try:
        users = _load_users()
        u = users.get(username)
        if not u:
            return False
        if u.get("is_default"):
            return True
        return _hash(DEFAULT_PWD, u.get("salt", "")) == u.get("pwd_hash", "")
    except Exception:
        return False


def _load_users():
    """全量用户读: SQLite(dbmanager.db)。启动时若检测到旧 users.json 则先迁移。"""
    sqlitedb.init_db()
    if os.path.exists(USERS_FILE):
        sqlitedb.migrate_users_json(USERS_FILE)
    return sqlitedb.users_load()


def _hash(pwd, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), bytes.fromhex(salt_hex), 120000).hex()


def _save(users):
    """原子写用户: SQLite 事务覆盖写入(与旧 JSON 原子写语义一致)"""
    sqlitedb.init_db()
    sqlitedb.users_save(users)


def ldap_auth(username, password):
    """LDAP/AD 认证: 成功返回 True, 失败返回 False。
    优先用绑定查询账号(BINDDN/BINDPW)按用户名查 DN 再验证; 无绑定账号时直接构造
    {attr}={username},{base} 绑定。ldap3 未安装 / 连接失败均返回 False(降级本地登录)。
    配置运行时读取: 管理界面修改 LDAP 项后即时生效。"""
    c = _ldap_cfg()
    if not (c["url"] and c["base"]):
        return False
    try:
        from ldap3 import Server, Connection, ALL
    except Exception:
        return False
    try:
        server = Server(c["url"], get_info=ALL)
        if c["binddn"]:
            # 两步: 先用绑定账号查用户 DN, 再以用户 DN 验证密码
            with Connection(server, user=c["binddn"], password=c["bindpw"], auto_bind=True, receive_timeout=5) as conn:
                conn.search(c["base"], "(%s=%s)" % (c["attr"], username), attributes=["distinguishedName"])
                if not conn.entries:
                    return False
                user_dn = str(conn.entries[0].distinguishedName)
        else:
            user_dn = "%s=%s,%s" % (c["attr"], username, c["base"])
        with Connection(server, user=user_dn, password=password, auto_bind=True, receive_timeout=5):
            return True
    except Exception:
        return False


def login(username, password, ip=""):
    """校验账号密码；返回三元组 (status, payload)：
    ('ok', (token, role, username)) / ('fail', None) / ('locked', 剩余秒数)
    / ('pending', None) 待审批 / ('rejected', None) 已拒绝
    限流：同一 IP+用户名 连续失败 MAX_FAIL 次锁 LOCK_SEC 秒
    认证顺序: 本地 users.json 优先(管理员/离线可用) -> LDAP(配置启用时) -> 失败"""
    key = "%s|%s" % (ip or "", username)
    now = time.time()
    f = LOGIN_FAIL.get(key)
    if f and f[0] >= LOGIN_MAX_FAIL:
        if now - f[1] < LOGIN_LOCK_SEC:
            return ("locked", int(LOGIN_LOCK_SEC - (now - f[1])))
        LOGIN_FAIL.pop(key, None)
    users = _load_users()
    u = users.get(username)
    if u and u.get("salt") and secrets.compare_digest(_hash(password, u["salt"]), u.get("pwd_hash", "")):
        LOGIN_FAIL.pop(key, None)
        status = u.get("status", "active")
        if status == "pending":
            return ("pending", None)
        if status == "rejected":
            return ("rejected", None)
        tok = secrets.token_hex(16)
        with _LOCK:
            USER_SESSIONS[tok] = _new_session_entry(username, u.get("role", "read"), ip)
        return ("ok", (tok, u.get("role", "read"), username))
    # 本地无此账号(或密码不符)且启用了 LDAP -> 走 AD 认证
    if ldap_enabled() and ldap_auth(username, password):
        LOGIN_FAIL.pop(key, None)
        role = users.get(username, {}).get("role", "read")  # LDAP 用户角色在 users.json 配置, 默认只读
        tok = secrets.token_hex(16)
        with _LOCK:
            USER_SESSIONS[tok] = _new_session_entry(username, role, ip)
        return ("ok", (tok, role, username))
    cnt, ts = f if f else (0, now)
    LOGIN_FAIL[key] = [cnt + 1, ts if cnt else now]
    if len(LOGIN_FAIL) > 10000:
        LOGIN_FAIL.clear()
    return ("fail", None)


def change_password(username, old_pwd, new_pwd):
    """修改当前用户密码；返回 (ok, message)"""
    users = _load_users()
    u = users.get(username)
    if not u or not u.get("salt") or not secrets.compare_digest(_hash(old_pwd, u["salt"]), u.get("pwd_hash", "")):
        return False, t("auth.old_pwd_wrong")
    if not new_pwd or len(new_pwd) < 6:
        return False, t("auth.new_pwd_min")
    salt = secrets.token_hex(16)
    u["pwd_hash"] = _hash(new_pwd, salt)
    u["salt"] = salt
    u.pop("is_default", None)  # 清除默认账号标记(强制改密完成)
    _save(users)
    return True, "密码已更新"


def list_users():
    """账号列表(不含哈希), 含审批状态(status)"""
    users = _load_users()
    return [
        {"username": k, "role": v.get("role", "read"), "status": v.get("status", "active")}
        for k, v in sorted(users.items())
    ]


def approve_user(username, role, action, cur_role=None):
    """审批自助注册账号: action=approve(批准并设角色) / reject(拒绝)
    cur_role: 调用者角色纵深校验(仅 admin 可审批与授予角色)。返回 (ok, message)"""
    users = _load_users()
    u = users.get(username)
    if not u:
        return False, t("auth.user_not_found")
    if u.get("status", "active") != "pending":
        return False, "该账号不是待审批状态"
    if cur_role not in (None, "admin"):
        return False, "仅管理员可审批账号"
    if action == "approve":
        if role not in ("read", "write", "admin"):
            return False, "角色仅支持 read/write/admin"
        if role == "admin" and cur_role not in (None, "admin"):
            return False, "仅管理员可授予 admin 角色"
        u["role"] = role
        u["status"] = "active"
        _save(users)
        return True, "已批准, 账号可登录"
    if action == "reject":
        u["status"] = "rejected"
        _save(users)
        return True, "已拒绝该账号"
    return False, "action 仅支持 approve/reject"


def save_user(username, role, password=None, cur_role=None):
    """新建或更新账号(password 非空则重置密码)；返回 (ok, message)
    管理员创建/更新的账号默认 active(可登录); 自助注册走 register()(pending)
    cur_role: 调用者角色; 纵深校验——非 admin 不得授予 admin 角色(即使路由门禁被放宽, 提权仍被拦截)"""
    users = _load_users()
    if not username or not re.match(r"^[\w\u4e00-\u9fff.\-]{2,32}$", username):
        return False, "用户名需 2-32 位(字母/数字/下划线/中文)"
    if role not in ("read", "write", "admin"):
        return False, "角色仅支持 read/write/admin"
    if role == "admin" and cur_role not in (None, "admin"):
        return False, "仅管理员可授予 admin 角色"
    if password:
        if len(password) < 6:
            return False, "密码至少 6 位"
        salt = secrets.token_hex(16)
        users[username] = {
            "pwd_hash": _hash(password, salt),
            "salt": salt,
            "role": users.get(username, {}).get("role", role),
            "status": "active",
        }
    elif username in users:
        users[username]["role"] = role
        users[username]["status"] = "active"  # 管理员调整角色即视为启用
    else:
        return False, "账号不存在(未提供初始密码)"
    _save(users)
    return True, "已保存"


def delete_user(username, cur_user):
    """删除账号；不能删除自己"""
    if username == cur_user:
        return False, t("auth.cannot_delete_self")
    users = _load_users()
    if username not in users:
        return False, "账号不存在"
    users.pop(username, None)
    _save(users)
    return True, t("auth.deleted")


# 自助注册限流: 同 IP 每窗口最多 MAX 次
REGISTER_FAIL = {}
REGISTER_MAX = 5
REGISTER_WINDOW = 3600  # 1 小时


def register(username, password, ip=""):
    """自助注册: 创建待审批账号(status=pending, 管理员批准后才能登录); 防滥用限流
    局域网定位默认开启; DBM_ALLOW_REGISTER=0 关闭时由管理员创建账号。返回 (ok, message)"""
    if not register_enabled():
        return False, "自助注册已关闭, 请联系管理员创建账号"
    if not auth_enabled():
        return False, "账号体系未启用"
    key = ip or "?"
    now = time.time()
    f = REGISTER_FAIL.get(key)
    if f and f[0] >= REGISTER_MAX and now - f[1] < REGISTER_WINDOW:
        return False, "注册过于频繁, 请 1 小时后再试"
    if not username or not re.match(r"^[\w\u4e00-\u9fff.\-]{2,32}$", username):
        return False, "用户名需 2-32 位(字母/数字/下划线/中文)"
    if not password or len(password) < 6:
        return False, "密码至少 6 位"
    users = _load_users()
    if username in users:
        return False, "用户名已存在"
    salt = secrets.token_hex(16)
    users[username] = {
        "pwd_hash": _hash(password, salt),
        "salt": salt,
        "role": "read",
        "status": "pending",
    }  # 待审批: 管理员 approve 后方可登录
    _save(users)
    cnt, ts = f if f else (0, now)
    REGISTER_FAIL[key] = [cnt + 1, ts if cnt else now]
    if len(REGISTER_FAIL) > 10000:
        REGISTER_FAIL.clear()
    return True, "注册已提交, 等待管理员审批后可登录"


def _cookie_token(cookie_header, name="dbm_user"):
    """从 Cookie 头解析指定 cookie 值(会话令牌)"""
    try:
        for part in (cookie_header or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name and v:
                return v
    except Exception:
        pass
    return None


def logout(token):
    """删除服务端会话(登出)"""
    if token:
        with _LOCK:
            USER_SESSIONS.pop(token, None)


def _new_session_entry(username, role, ip=""):
    """创建会话记录: 含登录时间/来源 IP/最后活跃(在线用户管理所需字段)"""
    now = time.time()
    return {
        "user": username,
        "role": role,
        "exp": now + SESSION_TTL,
        "login_time": now,
        "ip": ip or "",
        "last_active": now,
    }


def touch_activity(username, path):
    """记录用户最后操作路径(在线管理面板"当前操作"); 同路径 5 秒内不重复写(节流降锁竞争)"""
    if not username or not path or username == "-":
        return
    try:
        now = time.time()
        with _LOCK:
            a = USER_ACTIVITY.get(username)
            if a and a.get("_t", 0) > now - 5 and a.get("path") == path:
                return
            USER_ACTIVITY[username] = {"path": path, "_t": now}
            if len(USER_ACTIVITY) > 10000:
                USER_ACTIVITY.clear()
    except Exception:
        pass


def current_user(handler):
    """解析当前登录用户；未登录/过期返回 None
    令牌来源: 优先 HttpOnly Cookie dbm_user(浏览器自动携带, JS 不可读); 仅无 Cookie 时回退 X-User-Token 头(API 客户端/CI)
    开发模式 DBM_DEV=1: 无有效会话时默认视为 admin 已登录(便于调试登录态 UI, 无需输密码)"""
    # 优先 HttpOnly Cookie(dbm_user)——浏览器自动携带且 JS 不可读(XSS 安全);
    # 仅当无 Cookie(纯 API 客户端/CI/移动端)时回退到 X-User-Token 请求头(P0-4)。
    tok = _cookie_token(handler.headers.get("Cookie")) or handler.headers.get("X-User-Token")
    if tok:
        s = USER_SESSIONS.get(tok)
        if s:
            if time.time() > s["exp"]:
                with _LOCK:
                    USER_SESSIONS.pop(tok, None)
                return None
            # 节流更新最后活跃(在线用户管理): 30 秒粒度, 减少锁竞争
            if time.time() - s.get("last_active", 0) > 30:
                with _LOCK:
                    s["last_active"] = time.time()
            return s
    if conf("DBM_DEV") == "1":
        return {"user": "admin", "role": "admin"}
    return None


def user_name(handler):
    u = current_user(handler)
    return u["user"] if u else "-"


# ---------------------------------------------------------------------------
# 细粒度权限模型(连接级 + 表级读写): 管理员在 users.json 为用户配置 perms
#   users[user]["perms"] = {
#     "连接名": {"read": bool, "write": bool, "tables": [...], "deny_tables": [...]}
#   }
#   - read/write: 该连接读写开关(写操作需 write=true)
#   - tables: 表白名单(非空=仅这些表可见可操作; 空/缺省=全部表)
#   - deny_tables: 表黑名单(优先于白名单, 即使在白名单内也拒绝)
#   - admin 角色全量放行; 未配置 perms 的用户不受限(兼容老部署)
# ---------------------------------------------------------------------------


def user_perms(username):
    """返回指定用户的连接级权限配置: {连接名: {read, write, tables, deny_tables}}"""
    try:
        users = _load_users()
        return (users.get(username) or {}).get("perms") or {}
    except Exception:
        return {}


def set_user_perms(usernames, perms, cur_role=None):
    """批量设置用户权限(仅 admin): usernames 用户列表 + perms {连接名: {read, write, tables, deny_tables}}
    perms 为空 dict 表示清空这些用户的全部权限配置(恢复不受限)。返回 (ok, message)"""
    if cur_role not in (None, "admin"):
        return False, "仅管理员可配置权限"
    clean = {}
    for name, p in (perms or {}).items():
        if not isinstance(name, str) or not name.strip():
            continue
        d = {}
        if isinstance(p, dict):
            d["read"] = bool(p.get("read"))
            d["write"] = bool(p.get("write"))
            tl, dl = p.get("tables") or [], p.get("deny_tables") or []
            d["tables"] = sorted({str(x) for x in tl if x}) if isinstance(tl, (list, tuple)) else []
            d["deny_tables"] = sorted({str(x) for x in dl if x}) if isinstance(dl, (list, tuple)) else []
        clean[name.strip()] = d
    users = _load_users()
    miss = []
    for un in usernames or []:
        if un not in users:
            miss.append(un)
            continue
        if clean:
            users[un]["perms"] = clean
        else:
            users[un].pop("perms", None)  # 清空 = 恢复无限制(兼容老部署行为)
    _save(users)
    if miss:
        return True, "已保存(跳过不存在账号: %s)" % ", ".join(miss)
    return True, "已保存 %d 个用户的权限配置" % len(usernames or [])


def can_access(username, role, conn_name, action, table=None):
    """核心权限判定: 用户对 连接[.表] 的 read/write 权限
    - role == admin: 全量放行
    - 用户无 perms 配置(老部署/未配置): 放行(保持原有可见性行为)
    - 连接未在 perms 中: 拒绝(管理员配置了权限后, 只有被授权的连接可用)
    - action: 'read' 需 read=true; 'write' 需 write=true
    - table 非空时: deny_tables 黑名单优先; tables 白名单(非空)仅放行名单内"""
    if role == "admin":
        return True
    try:
        users = _load_users()
        p = (users.get(username) or {}).get("perms")
    except Exception:
        p = None
    if not p:
        return True
    cp = p.get(conn_name)
    if not cp:
        return False
    if action == "write":
        if not cp.get("write"):
            return False
    elif not cp.get("read"):
        return False
    if table:
        dl = cp.get("deny_tables") or []
        if table in dl:
            return False
        tl = cp.get("tables") or []
        if tl and table not in tl:
            return False
    return True


def list_sessions():
    """在线用户列表(按用户聚合): 用户名/角色/首次登录时间/来源IP/最后活跃/当前操作/会话数
    按最后活跃倒序(最近活跃在前)"""
    with _LOCK:
        sess = [dict(v) for v in USER_SESSIONS.values()]
    now = time.time()
    by_user = {}
    for s in sess:
        if now > s.get("exp", 0):
            continue
        key = s["user"]
        if key not in by_user:
            by_user[key] = {
                "user": key,
                "role": s.get("role", "read"),
                "login_time": s.get("login_time", 0),
                "ip": s.get("ip", ""),
                "last_active": s.get("last_active", 0),
                "sessions": 1,
            }
        else:
            by_user[key]["sessions"] += 1
            by_user[key]["login_time"] = min(by_user[key]["login_time"], s.get("login_time", 0))
            by_user[key]["last_active"] = max(by_user[key]["last_active"], s.get("last_active", 0))
    out = []
    for u in by_user.values():
        a = USER_ACTIVITY.get(u["user"])
        if a and a.get("path"):
            u["last_path"] = a["path"]
        out.append(u)
    return sorted(out, key=lambda x: -(x.get("last_active") or 0))


def kick_user(username, cur_user=None):
    """强制踢下线: 删除该用户全部会话(多设备同时登出); 不能踢自己"""
    if not username:
        return False, "参数错误"
    if username == cur_user:
        return False, "不能踢出当前登录账号"
    with _LOCK:
        n = 0
        for tok in [t for t, s in USER_SESSIONS.items() if s.get("user") == username]:
            USER_SESSIONS.pop(tok, None)
            n += 1
    if n == 0:
        return False, "该用户不在线"
    return True, "已强制下线: %s (%d 个会话)" % (username, n)
