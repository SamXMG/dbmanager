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
import json
import os
import re
import secrets
import threading
import time

from config import BASE_DIR

USERS_FILE = os.path.join(BASE_DIR, "users.json")
USER_SESSIONS = {}          # token -> {user, role, exp}
SESSION_TTL = 12 * 3600     # 登录会话 12 小时
_LOCK = threading.Lock()

# 登录限流: 同一 IP+用户名 连续失败 MAX_FAIL 次锁定 LOCK_SEC 秒
LOGIN_FAIL = {}
LOGIN_MAX_FAIL = 5
LOGIN_LOCK_SEC = 300

# 首次启用时的默认账号（管理员）——密码 admin123, 首次登录后请手工改 users.json
# 可用环境变量 DBM_DEFAULT_PWD 覆盖首次创建的默认密码(仅首次建库生效, 之后修改请走改密接口)
DEFAULT_USER = "admin"
DEFAULT_PWD = os.environ.get("DBM_DEFAULT_PWD") or "admin123"

# LDAP/AD 接入（内网可选）: 配置后 LDAP 用户可直接登录, users.json 管理角色与本地管理员
LDAP_URL = os.environ.get("DBM_LDAP_URL", "")       # 如 ldap://192.168.1.10:389
LDAP_BASE = os.environ.get("DBM_LDAP_BASE", "")     # 如 dc=company,dc=com
LDAP_BINDDN = os.environ.get("DBM_LDAP_BINDDN", "")  # 可选: 绑定查询账号(有则先按用户名查 DN)
LDAP_BINDPW = os.environ.get("DBM_LDAP_BINDPW", "")
LDAP_ATTR = os.environ.get("DBM_LDAP_ATTR", "sAMAccountName")  # 用户名属性(AD 默认, OpenLDAP 常用 uid)


def ldap_enabled():
    """LDAP 接入是否启用(需 URL + BASE)"""
    return bool(LDAP_URL and LDAP_BASE)


def register_enabled():
    """自助注册开关: 默认关闭(内网合规, 账号由管理员创建), DBM_ALLOW_REGISTER=1 开启"""
    return os.environ.get("DBM_ALLOW_REGISTER") == "1"


def auth_enabled():
    """启用条件：users.json 存在或环境变量 DBM_AUTH=1。
    注意: 启动时 ensure_default() 会自动创建 users.json → 默认即启用认证(默认口令 admin123)。
    顺带执行幂等迁移: 默认 admin 账号角色升级为 admin(内网管理权限)。"""
    _migrate_admin_role()
    if os.environ.get("DBM_AUTH") == "1":
        return True
    return os.path.exists(USERS_FILE)


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
    """users.json 不存在时创建默认管理员账号（首次部署自动生成, 调用方应据此提示改密）
    返回 True=本次新建默认账号(需提示改密), False=已有部署(仅平滑迁移 admin 角色)。"""
    if os.path.exists(USERS_FILE):
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
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            # is_default: 默认账号标记(强制首改密依据), 改密成功后清除
            json.dump({DEFAULT_USER: {"pwd_hash": h, "salt": salt, "role": "admin",
                                      "is_default": True}},
                      f, ensure_ascii=False, indent=2)
        os.chmod(USERS_FILE, 0o600)
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
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _hash(pwd, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"),
                               bytes.fromhex(salt_hex), 120000).hex()


def _save(users):
    """原子写 users.json(临时文件+replace, 防并发写坏)"""
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    os.replace(tmp, USERS_FILE)


def ldap_auth(username, password):
    """LDAP/AD 认证: 成功返回 True, 失败返回 False。
    优先用绑定查询账号(BINDDN/BINDPW)按用户名查 DN 再验证; 无绑定账号时直接构造
    {attr}={username},{base} 绑定。ldap3 未安装 / 连接失败均返回 False(降级本地登录)。"""
    try:
        from ldap3 import Server, Connection, ALL
        import ldap3
    except Exception:
        return False
    try:
        server = Server(LDAP_URL, get_info=ALL)
        if LDAP_BINDDN:
            # 两步: 先用绑定账号查用户 DN, 再以用户 DN 验证密码
            with Connection(server, user=LDAP_BINDDN, password=LDAP_BINDPW,
                            auto_bind=True, receive_timeout=5) as conn:
                conn.search(LDAP_BASE, "(%s=%s)" % (LDAP_ATTR, username),
                            attributes=["distinguishedName"])
                if not conn.entries:
                    return False
                user_dn = str(conn.entries[0].distinguishedName)
        else:
            user_dn = "%s=%s,%s" % (LDAP_ATTR, username, LDAP_BASE)
        with Connection(server, user=user_dn, password=password,
                        auto_bind=True, receive_timeout=5):
            return True
    except Exception:
        return False


def login(username, password, ip=""):
    """校验账号密码；返回三元组 (status, payload)：
    ('ok', (token, role, username)) / ('fail', None) / ('locked', 剩余秒数)
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
    if u and u.get("salt") and secrets.compare_digest(
            _hash(password, u["salt"]), u.get("pwd_hash", "")):
        LOGIN_FAIL.pop(key, None)
        tok = secrets.token_hex(16)
        with _LOCK:
            USER_SESSIONS[tok] = {"user": username,
                                  "role": u.get("role", "read"),
                                  "exp": time.time() + SESSION_TTL}
        return ("ok", (tok, u.get("role", "read"), username))
    # 本地无此账号(或密码不符)且启用了 LDAP -> 走 AD 认证
    if ldap_enabled() and ldap_auth(username, password):
        LOGIN_FAIL.pop(key, None)
        role = users.get(username, {}).get("role", "read")  # LDAP 用户角色在 users.json 配置, 默认只读
        tok = secrets.token_hex(16)
        with _LOCK:
            USER_SESSIONS[tok] = {"user": username,
                                  "role": role,
                                  "exp": time.time() + SESSION_TTL}
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
    if not u or not u.get("salt") or not secrets.compare_digest(
            _hash(old_pwd, u["salt"]), u.get("pwd_hash", "")):
        return False, "旧密码错误"
    if not new_pwd or len(new_pwd) < 6:
        return False, "新密码至少 6 位"
    salt = secrets.token_hex(16)
    u["pwd_hash"] = _hash(new_pwd, salt)
    u["salt"] = salt
    u.pop("is_default", None)   # 清除默认账号标记(强制改密完成)
    _save(users)
    return True, "密码已更新"


def list_users():
    """账号列表(不含哈希)"""
    users = _load_users()
    return [{"username": k, "role": v.get("role", "read")}
            for k, v in sorted(users.items())]


def save_user(username, role, password=None, cur_role=None):
    """新建或更新账号(password 非空则重置密码)；返回 (ok, message)
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
        users[username] = {"pwd_hash": _hash(password, salt),
                           "salt": salt,
                           "role": users.get(username, {}).get("role", role)}
    elif username in users:
        users[username]["role"] = role
    else:
        return False, "账号不存在(未提供初始密码)"
    _save(users)
    return True, "已保存"


def delete_user(username, cur_user):
    """删除账号；不能删除自己"""
    if username == cur_user:
        return False, "不能删除当前登录账号"
    users = _load_users()
    if username not in users:
        return False, "账号不存在"
    users.pop(username, None)
    _save(users)
    return True, "已删除"


# 自助注册限流: 同 IP 每窗口最多 MAX 次
REGISTER_FAIL = {}
REGISTER_MAX = 5
REGISTER_WINDOW = 3600  # 1 小时


def register(username, password, ip=""):
    """自助注册(仅创建只读账号, 防滥用限流)；返回 (ok, message)
    内网默认关闭: 需 DBM_ALLOW_REGISTER=1 开启, 否则由管理员在账号管理页创建。"""
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
    users[username] = {"pwd_hash": _hash(password, salt),
                       "salt": salt, "role": "read"}  # 注册默认只读, 升级需 write 管理员
    _save(users)
    cnt, ts = f if f else (0, now)
    REGISTER_FAIL[key] = [cnt + 1, ts if cnt else now]
    if len(REGISTER_FAIL) > 10000:
        REGISTER_FAIL.clear()
    return True, "账号已创建(只读权限), 请登录"


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


def current_user(handler):
    """解析当前登录用户；未登录/过期返回 None
    令牌来源: X-User-Token 请求头(API 客户端/旧前端) 或 HttpOnly Cookie dbm_user(浏览器自动携带)
    开发模式 DBM_DEV=1: 无有效会话时默认视为 admin 已登录(便于调试登录态 UI, 无需输密码)"""
    tok = handler.headers.get("X-User-Token") or _cookie_token(handler.headers.get("Cookie"))
    if tok:
        s = USER_SESSIONS.get(tok)
        if s:
            if time.time() > s["exp"]:
                with _LOCK:
                    USER_SESSIONS.pop(tok, None)
                return None
            return s
    if os.environ.get("DBM_DEV") == "1":
        return {"user": "admin", "role": "admin"}
    return None


def user_name(handler):
    u = current_user(handler)
    return u["user"] if u else "-"
