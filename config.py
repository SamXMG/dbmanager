# -*- coding: utf-8 -*-
"""dbmanager - 配置与共享状态
所有常量、路径、缓存容器、线程锁与驱动选择逻辑集中于此。
其他模块统一 `from config import ...` 引用, 保证多线程共享同一实例。

配置优先级(统一走 conf()): 环境变量 > dbmanager.conf 配置文件 > 内置默认值。
- 环境变量保留给 CI/Docker/临时覆盖(DBM_* 全部兼容);
- 日常配置写项目根 dbmanager.conf(UTF-8, INI 格式, 见文件内注释), 改一次永久生效;
- 敏感项(网关令牌/默认密码/LDAP 密码)建议留空, 由系统自动生成或走页面配置。
"""
import configparser
import os
import threading

# 基础路径(所有模块共用, 各模块据此定位同目录文件)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
SERVERS = []  # 由 app.run() 赋值(IPv4/IPv6 监听实例), 供 shutdown 接口读取

# ------------------------------
# 配置文件(dbmanager.conf)
# ------------------------------
# 环境变量 DBM_CONF 可指定自定义配置文件路径(便于 CI/容器挂载卷覆盖)
def _config_path():
    return os.environ.get("DBM_CONF") or os.path.join(BASE_DIR, "dbmanager.conf")

_CONFIG_CACHE = None  # configparser 实例, 进程内仅加载一次(改配置需重启生效)

def _load_config():
    """惰性加载 dbmanager.conf(UTF-8); 文件不存在/解析失败时返回空配置, 不影响启动。"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        cfg = configparser.ConfigParser()
        cfg.optionxform = str  # 保留键原始大小写
        try:
            cfg.read(_config_path(), encoding="utf-8")
        except Exception:
            pass
        _CONFIG_CACHE = cfg
    return _CONFIG_CACHE

# 环境变量名 -> (配置文件 section, 配置文件 key, 内置默认值)
# 约定: key 与 DBM_ 去掉前缀后同名(小写), 便于记忆; 敏感项默认留空由系统自动管理
_ENV_MAP = {
    # [server]
    "DBM_HOST": ("server", "host", "127.0.0.1"),
    "DBM_PORT": ("server", "port", "8770"),
    "DBM_DB_FILE": ("server", "db_file", ""),
    "DBM_DEV": ("server", "dev", ""),
    "DBM_LOG": ("server", "log", ""),
    "DBM_NO_OPEN": ("server", "no_open", ""),
    "DBM_NO_KILL": ("server", "no_kill", ""),
    "DBM_SSL": ("server", "ssl", ""),
    "DBM_SSL_CERT": ("server", "ssl_cert", ""),
    "DBM_SSL_KEY": ("server", "ssl_key", ""),
    "DBM_GATEWAY_TOKEN": ("server", "gateway_token", ""),
    "DBM_DEFAULT_CONN": ("server", "default_conn", ""),
    # [auth]
    "DBM_DEFAULT_PWD": ("auth", "default_pwd", ""),
    "DBM_ALLOW_REGISTER": ("auth", "allow_register", ""),
    "DBM_AUTH": ("auth", "auth_enabled", ""),
    "DBM_LDAP_URL": ("auth", "ldap_url", ""),
    "DBM_LDAP_BASE": ("auth", "ldap_base", ""),
    "DBM_LDAP_BINDDN": ("auth", "ldap_binddn", ""),
    "DBM_LDAP_BINDPW": ("auth", "ldap_bindpw", ""),
    "DBM_LDAP_ATTR": ("auth", "ldap_attr", "sAMAccountName"),
}

def conf(name):
    """统一配置读取: 环境变量 > dbmanager.conf > 内置默认值。返回字符串(与 os.environ.get 语义一致)。
    未注册的 key 仅读环境变量(向后兼容)。"""
    spec = _ENV_MAP.get(name)
    if spec is None:
        return os.environ.get(name, "")
    section, key, default = spec
    v = os.environ.get(name)
    if v is not None and v != "":
        return v
    try:
        val = _load_config().get(section, key, fallback=default)
    except Exception:
        val = default
    return val if val is not None else default

def conf_int(name):
    """conf() 的整数版本; 解析失败回退默认值。"""
    try:
        return int(conf(name))
    except (TypeError, ValueError):
        try:
            return int(_ENV_MAP[name][2])
        except Exception:
            return 0

def conf_bool(name):
    """conf() 的布尔版本: 值 == "1"/"true"/"yes"(忽略大小写) 视为真。"""
    return conf(name).strip().lower() in ("1", "true", "yes")

# ------------------------------
# 运行时配置(读取后不可在运行中热改)
# ------------------------------
# 安全默认: 仅监听本机(五轮评估 P2-1 收敛暴露面); 需局域网/公网访问时在 dbmanager.conf 将 host 改为 0.0.0.0
# (或临时 DBM_HOST=0.0.0.0 覆盖)
HOST = conf("DBM_HOST")
PORT = conf_int("DBM_PORT")
LOCK = threading.Lock()

# 前端静态资源: 子目录 -> (目录名, Content-Type); 仅白名单扁平文件
STATIC_DIRS = {
    "/css/": ("css", "text/css; charset=utf-8"),
    "/js/": ("js", "application/javascript; charset=utf-8"),
}

# Vue3 迁移版(frontend/ 子目录, 与旧前端并存; /v2 入口 serve 其构建产物)
VUE_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")
VUE_INDEX_FILE = os.path.join(VUE_DIST_DIR, "index.html")

ENGINE_CACHE = {}          # hash -> Engine
ENGINE_CACHE_MAX = 32      # 引擎缓存上限, 超出丢弃最旧(防长期运行连接池无限累积)
TX_CONN = {}               # hash -> (Connection, Engine)  事务模式下的持久连接
SESSIONS = {}              # token -> (已解析连接, 创建时间); 密码仅存服务端内存, 用于按名直连
SESSION_TTL = 12 * 3600    # 会话有效期 12 小时, 过期需重新连接
CONN_IDLE_TIMEOUT = 1800   # 30 分钟闲置自动回收
QUERY_TIMEOUT = 30         # 查询超时(秒)

# 版本(语义化): 主版本.次版本.补丁; 发版时同步 frontend/package.json 与 CHANGELOG.md
VERSION = "1.5.0"

DEFAULT_PORT = {"mysql": 3306, "postgresql": 5432, "mssql": 1433, "oracle": 1521}
DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"
SUPPORTED = ("sqlite", "mysql", "postgresql", "mssql", "oracle", "mongodb", "redis")

_ODBC_DRIVERS_CACHE = None  # 本机已安装 ODBC 驱动列表(惰性缓存)

def _odbc_drivers():
    """返回本机已安装的 ODBC 驱动列表；pyodbc 缺失时返回空列表"""
    global _ODBC_DRIVERS_CACHE
    if _ODBC_DRIVERS_CACHE is None:
        try:
            import pyodbc
            _ODBC_DRIVERS_CACHE = pyodbc.drivers()
        except Exception:
            _ODBC_DRIVERS_CACHE = []
    return _ODBC_DRIVERS_CACHE

def _pick_mssql_driver():
    """按优先级选择本机可用的 SQL Server 驱动：ODBC Driver 18 > 17 > Native Client > SQL Server"""
    avail = _odbc_drivers()
    for name in ("ODBC Driver 18 for SQL Server",
                 "ODBC Driver 17 for SQL Server",
                 "SQL Server Native Client 11.0",
                 "SQL Native Client",
                 "SQL Server"):
        if name in avail:
            return name
    return None

def _mysql_scheme():
    """MySQL/MariaDB 连接串前缀：优先用官方 mariadb 连接器(支持 GSSAPI 等)，
    未安装时回退到纯 Python 的 pymysql。"""
    try:
        import mariadb  # noqa: F401
        return "mariadb+mariadbconnector"
    except Exception:
        return "mysql+pymysql"

