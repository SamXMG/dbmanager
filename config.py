# -*- coding: utf-8 -*-
"""dbmanager - 配置与共享状态
所有常量、路径、缓存容器、线程锁与驱动选择逻辑集中于此。
其他模块统一 `from config import ...` 引用, 保证多线程共享同一实例。
"""
import os
import threading

# 基础路径(所有模块共用, 各模块据此定位同目录文件)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
SERVERS = []  # 由 app.run() 赋值(IPv4/IPv6 监听实例), 供 shutdown 接口读取

# ------------------------------
# 配置
# ------------------------------
# 安全默认: 仅监听本机(五轮评估 P2-1 收敛暴露面); 需局域网/公网访问时显式 DBM_HOST=0.0.0.0
HOST = os.environ.get("DBM_HOST", "127.0.0.1")
PORT = int(os.environ.get("DBM_PORT", "8770"))
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

