# -*- coding: utf-8 -*-
"""dbmanager - ops 基础层: 安全/工具/元数据缓存/标识符引用/SQL拆分"""
import re
import time

from config import LOCK

# 只读模式允许/阻止的 SQL 首关键字
SQL_READ_ONLY = ("select", "show", "explain", "desc", "describe")
SQL_BLOCKED = ("insert", "update", "delete", "drop", "alter", "create",
               "truncate", "grant", "revoke", "exec", "execute", "merge",
               "replace", "call", "backup", "restore")


def escape_identifier(s: str) -> str:
    """转义 SQL 标识符中的 ], 防止注入"""
    return s.replace("]", "]]")

def safe_where_clause(where: str, valid_columns: list) -> str:
    """ 安全校验 WHERE 条件(不含 WHERE 关键字)
    - 禁止多语句、注释
    - 所有标识符必须在有效字段列表中
    返回清洗后的条件片段(不含 "WHERE " 前缀)"""
    if not where or not where.strip():
        return ""
    w = where.strip()
    if re.search(r"(--|/\*|\*/|;)", w, re.I):
        raise ValueError("筛选条件禁止包含注释符( -- /* */ )和分号")
    stripped = re.sub(r"'[^']*'", "''", w)  # 去掉字符串字面量，避免误判为字段
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", stripped)
    sql_keywords = {"and", "or", "not", "in", "like", "between", "is", "null", "true", "false",
                    "asc", "desc", "order", "by", "group", "having", "as",
                    "getdate", "dateadd", "datediff", "datepart", "year", "month", "day",
                    "len", "length", "charindex", "substring", "substr", "left", "right",
                    "upper", "lower", "trim", "ltrim", "rtrim", "replace", "concat",
                    "cast", "convert", "coalesce", "nullif", "isnull", "case", "when",
                    "then", "else", "end", "abs", "round", "floor", "ceiling",
                    "count", "sum", "avg", "max", "min", "distinct",
                    "now", "current_date", "current_timestamp", "current_user",
                    "exists", "any", "all", "some", "union"}
    valid_lower = {c.lower() for c in valid_columns}
    for token in tokens:
        tl = token.lower()
        if tl in sql_keywords:
            continue
        if tl not in valid_lower:
            raise ValueError(f"筛选条件包含未知字段或非法关键字: {token}")
    w = re.sub(r"^\s*where\s+", "", w, flags=re.I)
    return w

def py_to_json(v):
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", "ignore")
        except Exception:
            return repr(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)

# ------------------------------
# 元数据(跨库统一, 基于 SQLAlchemy inspect; 带 60s TTL 缓存避免反复反射)
# ------------------------------
META_CACHE = {}
META_TTL = 60
META_MAX = 300

def _meta_key(*parts):
    return "|".join(str(p) for p in parts)

def _meta_get(key):
    item = META_CACHE.get(key)
    if item and time.time() - item[1] < META_TTL:
        return item[0]
    return None

def _meta_set(key, val):
    if len(META_CACHE) > META_MAX:
        META_CACHE.clear()
    META_CACHE[key] = (val, time.time())

def _clear_count_cache(h, schema, table):
    """数据变更后清除指定表的 count 缓存, 保证翻页总数即时准确"""
    prefix = _meta_key("cnt", h, schema, table) + "|"
    with LOCK:
        for k in list(META_CACHE.keys()):
            if k.startswith(prefix):
                META_CACHE.pop(k, None)

# ------------------------------
# MongoDB: 文档范式, 独立 pymongo 路径(不走 SQLAlchemy); 复用 columns/rows 结构渲染
def _qi(t, name):
    """按方言引用标识符"""
    if t == "mssql":
        return "[" + str(name).replace("]", "]]") + "]"
    if t == "mysql":
        return "`" + str(name).replace("`", "``") + "`"
    return '"' + str(name).replace('"', '""') + '"'

def _check_type(s):
    if not re.fullmatch(r"[A-Za-z0-9_(), ]+", s or ""):
        raise ValueError("非法数据类型")
    return s.strip()

def _check_default(s):
    if re.search(r"[;/\-]{2}|--|\*/", s or ""):
        raise ValueError("非法默认值")
    return str(s).strip()

def split_sql_statements(sql):
    """按分号拆分多条 SQL, 跳过字符串/行注释/块注释内的分号"""
    stmts, cur = [], []
    in_str, in_line_c, in_block_c = None, False, False
    i, n = 0, len(sql)
    while i < n:
        ch, nx = sql[i], sql[i + 1] if i + 1 < n else ''
        if in_line_c:
            if ch == '\n':
                in_line_c = False
            cur.append(ch); i += 1; continue
        if in_block_c:
            cur.append(ch)
            if ch == '*' and nx == '/':
                cur.append(nx); in_block_c = False; i += 2; continue
            i += 1; continue
        if in_str:
            cur.append(ch)
            if ch == in_str:
                if nx == in_str:      # 双引号转义('' 或 ""), 跳过下一个
                    cur.append(nx); i += 2; continue
                in_str = None
            i += 1; continue
        if ch in ("'", '"', '`'):
            in_str = ch; cur.append(ch); i += 1; continue
        if ch == '-' and nx == '-':
            in_line_c = True; cur.append(ch); cur.append(nx); i += 2; continue
        if ch == '/' and nx == '*':
            in_block_c = True; cur.append(ch); cur.append(nx); i += 2; continue
        if ch == ';':
            s = ''.join(cur).strip()
            if s:
                stmts.append(s)
            cur = []
            i += 1; continue
        cur.append(ch); i += 1
    s = ''.join(cur).strip()
    if s:
        stmts.append(s)
    return stmts


# ------------------------------
# 表结构对比/同步: 源库 -> 目标库 的差异清单与可执行 DDL
# ------------------------------
def _col_ddl(col, nullable_override=None):
    """列定义(类型 + 可空), 不含默认值(避免方言默认值语法坑)"""
    n = col.get("nullable", True) if nullable_override is None else nullable_override
    return str(col["type"]) + (" NULL" if n else " NOT NULL")


