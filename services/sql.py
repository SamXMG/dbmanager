# -*- coding: utf-8 -*-
"""dbmanager - ops SQL 控制台: 多语句拆分执行/只读校验/写模式事务/执行计划"""
import re
import json

from sqlalchemy import text

from db.dbcore import get_engine
from services.core import SQL_BLOCKED, SQL_READ_ONLY, split_sql_statements

def run_sql(ci, sql, limit=500, write=False):
    """查询控制台: 支持多条分号分隔语句, 每条结果独立返回(前端各占一个 tab)。
    write=False(默认) 仅允许只读语句(SELECT/SHOW/EXPLAIN/DESC);
    write=True  允许任意语句(写模式), 整批语句事务包裹, 任一条失败整体回滚。
    注意: MySQL/MSSQL 的 DDL 会隐式提交, 无法回滚; DML 在事务内可回滚。"""
    if (ci.get("db_type") or "").lower() in ("mongodb", "redis"):
        raise ValueError("%s 不支持 SQL 查询，请在「数据」页打开%s浏览数据" % (
            "MongoDB" if ci.get("db_type") == "mongodb" else "Redis",
            "集合" if ci.get("db_type") == "mongodb" else "键"))
    limit = max(1, min(int(limit), 5000))
    s = (sql or "").strip()
    if not s:
        raise ValueError("SQL 不能为空")
    stmts = split_sql_statements(s)
    if not stmts:
        raise ValueError("SQL 不能为空")
    db_type = (ci.get("db_type") or "").lower()

    def _exec_one(conn, st):
        first = st.split(None, 1)[0].lower()
        sql_text = st
        # 防大表 SELECT 拖垮服务: 无 LIMIT 的 SELECT 自动追加(MySQL/PG/SQLite 支持;
        # MSSQL/Oracle 不支持 LIMIT 语法, 由下方 fetchmany 兜底截断)
        if first == "select" and db_type not in ("mssql", "oracle") \
                and not re.search(r"\blimit\b\s*[0-9?]", sql_text, re.I):
            sql_text = sql_text.rstrip().rstrip(";") + f" LIMIT {limit + 1}"
        result = conn.execute(text(sql_text))
        if result.returns_rows:
            cols = list(result.keys())
            # fetchmany 只物化 limit+1 行, 绝不把整表拉进内存
            rows = [dict(r) for r in result.mappings().fetchmany(limit + 1)]
            truncated = len(rows) > limit
            rows = rows[:limit]
            result.close()
            return {"sql": st, "columns": [{"name": c} for c in cols],
                    "rows": rows, "total": len(rows),
                    "truncated": truncated, "ok": True}
        affected = result.rowcount or 0
        result.close()
        return {"sql": st, "columns": [], "rows": [], "total": 0,
                "affected": affected, "ok": True}

    if not write:
        # 只读模式: 预校验全部语句都是只读才执行(一条违规则整批拒绝, 避免执行一半)
        for st in stmts:
            first = st.split(None, 1)[0].lower()
            if first in SQL_BLOCKED:
                raise ValueError("查询控制台仅支持只读查询, 已阻止语句: " + first.upper())
            if first not in SQL_READ_ONLY:
                raise ValueError("仅支持 SELECT / SHOW / EXPLAIN / DESC 开头的只读查询: " + st[:60])
            # SELECT INTO 绕过防护: MSSQL 的 SELECT...INTO 建表 / MySQL 的 INTO OUTFILE|DUMPFILE 写文件
            # 均可在只读模式下绕过高危操作; 仅放行 INTO @变量(MySQL 赋值)与 INTO DUAL(Oracle)
            if " INTO " in st.upper():
                rest = st.upper().split(" INTO ", 1)[1].strip()
                if not (rest.startswith("@") or rest.startswith("DUAL")):
                    raise ValueError("只读模式禁止 SELECT INTO(建表/写文件), 已阻止: " + st[:60])
        engine = get_engine(ci)
        results = []
        with engine.connect() as conn:
            for st in stmts:
                results.append(_exec_one(conn, st))
        return {"ok": True, "results": results, "readonly": True}

    # 写模式: 整批事务包裹, 任一条失败整体回滚(避免执行一半的脏状态)
    engine = get_engine(ci)
    results = []
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            for st in stmts:
                results.append(_exec_one(conn, st))
            tx.commit()
        except Exception:
            tx.rollback()
            raise
    return {"ok": True, "results": results, "readonly": False}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pg_buffers(node):
    """拼接 PG EXPLAIN ANALYZE BUFFERS 的块统计(仅 ANALYZE 时存在)"""
    parts = []
    for k, v in node.items():
        if k.endswith("Blocks") and v:
            short = k.replace(" Blocks", "").replace(" ", "_").lower()
            parts.append("%s=%s" % (short, v))
    return "; ".join(parts) if parts else None


def _normalize_pg_plan(node):
    """PG EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) 节点 -> 统一 PlanNode(不丢弃信息)"""
    if not isinstance(node, dict):
        return None
    detail = node.get("Index Cond") or node.get("Recheck Cond")
    if detail is None and node.get("Heap Fetches") is not None:
        detail = "Heap Fetches=" + str(node.get("Heap Fetches"))
    children = [_normalize_pg_plan(c) for c in node.get("Plans", [])]
    children = [c for c in children if c]
    return {
        "operation": node.get("Node Type", ""),
        "object": node.get("Relation Name") or node.get("Index Name") or None,
        "rows_est": node.get("Plan Rows"),
        "rows_actual": node.get("Actual Rows"),
        "cost_est": node.get("Total Cost"),
        "time_actual_ms": node.get("Actual Total Time"),
        "loops": node.get("Actual Loops"),
        "buffers": _pg_buffers(node),
        "filter": node.get("Filter") or node.get("Join Filter") or None,
        "detail": detail,
        "children": children,
    }


def _mysql_cost(obj):
    ci = obj.get("cost_info") or {}
    return _num(ci.get("prefix_cost") or ci.get("query_cost") or ci.get("read_cost"))


def _normalize_mysql_plan(obj, op="QUERY"):
    """MySQL EXPLAIN FORMAT=JSON -> 统一 PlanNode(估算, 无实际时间/行数)"""
    if not isinstance(obj, dict):
        return None
    if "query_block" in obj:
        blk = obj["query_block"]
        node = _normalize_mysql_plan(blk, op)
        if node:
            if "select_id" in blk:
                node["operation"] = "SELECT #%s" % blk["select_id"]
            if "cost_info" in blk and "query_cost" in blk["cost_info"]:
                node["cost_est"] = _num(blk["cost_info"]["query_cost"])
        return node
    if "materialized_from_subquery" in obj:
        inner = _normalize_mysql_plan(obj["materialized_from_subquery"], "MATERIALIZED")
        return {"operation": "MATERIALIZED SUBQUERY", "object": None,
                "rows_est": None, "rows_actual": None, "cost_est": None,
                "time_actual_ms": None, "loops": None, "buffers": None,
                "filter": None, "detail": None, "children": [inner] if inner else []}
    if "nested_loop" in obj:
        kids = [_normalize_mysql_plan(x) for x in obj["nested_loop"]]
        kids = [k for k in kids if k]
        return {"operation": "NESTED LOOP JOIN", "object": None,
                "rows_est": obj.get("rows_examined_per_scan"),
                "rows_actual": None, "cost_est": _mysql_cost(obj),
                "time_actual_ms": None, "loops": None, "buffers": None,
                "filter": obj.get("attached_condition"), "detail": None, "children": kids}
    if "table" in obj:
        t = obj["table"]
        if not isinstance(t, dict):
            t = obj
        ci = t.get("cost_info") or {}
        return {"operation": (t.get("access_type") or "unknown").upper() + " ACCESS",
                "object": t.get("table_name"),
                "rows_est": t.get("rows_examined_per_scan"),
                "rows_actual": None,
                "cost_est": _num(ci.get("prefix_cost") or ci.get("read_cost")),
                "time_actual_ms": None, "loops": None, "buffers": None,
                "filter": t.get("attached_condition"),
                "detail": ("key=" + t["key"]) if t.get("key") else None,
                "children": []}
    return {"operation": op, "object": None, "rows_est": None, "rows_actual": None,
            "cost_est": None, "time_actual_ms": None, "loops": None, "buffers": None,
            "filter": None, "detail": str(obj)[:200], "children": []}


def explain_query(ci, sql):
    """执行计划: PG/MySQL 返回归一化 plan 树(mode=tree, 前端树渲染);
    SQLite 返回结构化行, MSSQL/Oracle 返回文本行(mode=text)"""
    if (ci.get("db_type") or "").lower() in ("mongodb", "redis"):
        raise ValueError("Redis 无 SQL 执行计划" if ci.get("db_type") == "redis"
                         else "MongoDB 无 SQL 执行计划")
    db_type = (ci.get("db_type") or "mysql").lower()
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("SQL 不能为空")
    engine = get_engine(ci)
    with engine.connect() as conn:
        if db_type == "mysql":
            # 优先返回结构化 JSON 树(归一化为统一节点); 解析失败再退回传统表格
            try:
                rj = conn.execute(text("EXPLAIN FORMAT=JSON " + s))
                row = rj.fetchone()
                raw = row[0] if row else None
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except Exception:
                        raw = None
                tree = _normalize_mysql_plan(raw) if isinstance(raw, dict) else None
                if tree:
                    return {"mode": "tree", "dialect": "mysql", "plan": tree,
                            "columns": [], "rows": [], "total": 0}
            except Exception:
                pass
            result = conn.execute(text("EXPLAIN " + s))
            cols = [c for c in result.keys()]
            rows = [dict(r) for r in result.mappings()]
            return {"columns": [{"name": c} for c in cols], "rows": rows, "total": len(rows), "mode": "table"}
        if db_type == "postgresql":
            first = s.split(None, 1)[0].lower()
            tree = None
            if first == "select":
                # SELECT 用 ANALYZE,BUFFERS 拿到真实耗时/行数/缓冲(只读 SELECT 不会修改数据)
                try:
                    rj = conn.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + s))
                    plan = rj.scalar()
                    if isinstance(plan, list) and plan and isinstance(plan[0], dict):
                        tree = _normalize_pg_plan(plan[0])
                except Exception:
                    tree = None
            if not tree:
                # 非 SELECT 或 ANALYZE 失败 -> 纯估算(无实际时间/行数)
                rj = conn.execute(text("EXPLAIN (FORMAT JSON) " + s))
                plan = rj.scalar()
                if isinstance(plan, list) and plan and isinstance(plan[0], dict):
                    tree = _normalize_pg_plan(plan[0])
            if tree:
                return {"mode": "tree", "dialect": "postgresql", "plan": tree,
                        "columns": [], "rows": [], "total": 0}
            return {"columns": [{"name": "执行计划"}],
                    "rows": [{"执行计划": "无法解析执行计划"}], "total": 1, "mode": "text"}
        if db_type == "mssql":
            # MSSQL 限制: SHOWPLAN 开关必须是批次唯一语句(1067) -> 同连接分三次执行
            try:
                conn.execute(text("SET SHOWPLAN_ALL ON"))
                result = conn.execute(text(s))
                rows = [dict(r) for r in result.mappings().fetchmany(500)]
            finally:
                try:
                    conn.execute(text("SET SHOWPLAN_ALL OFF"))
                except Exception:
                    pass
            return {"columns": [{"name": c} for c in (list(rows[0].keys()) if rows else ["StmtText"])],
                    "rows": rows, "total": len(rows), "mode": "text"}
        if db_type == "oracle":
            # Oracle: EXPLAIN PLAN FOR 写入 PLAN_TABLE, 再读 DBMS_XPLAN 文本
            conn.execute(text("EXPLAIN PLAN FOR " + s))
            result = conn.execute(text("SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY(FORMAT=>'TYPICAL'))")).mappings()
            rows = [dict(r) for r in result.fetchmany(200)]
            txt = "\n".join(str(r.get(list(r.keys())[0]) or "") for r in rows)
            return {"columns": [{"name": "执行计划"}],
                    "rows": [{"执行计划": line} for line in txt.splitlines() if line.strip()],
                    "total": len(rows), "mode": "text"}
        # sqlite
        result = conn.execute(text("EXPLAIN QUERY PLAN " + s))
        rows = [dict(r) for r in result.mappings()]
        return {"columns": [{"name": c} for c in result.keys()], "rows": rows,
                "total": len(rows), "mode": "table"}

