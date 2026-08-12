# -*- coding: utf-8 -*-
"""dbmanager - ops 数据层: 分页查询/增删改/事务提交回滚(含Mongo/Redis分支)"""
from sqlalchemy import and_, delete, func, insert, select, text, true as sa_true, update

from config import LOCK, TX_CONN
from dbcore import conn_hash, get_connection, get_engine
from services.core import _clear_count_cache, _meta_get, _meta_key, _meta_set, py_to_json, safe_where_clause
from services.metadata import get_columns, get_pk, get_table_obj
from services.nosql import _mongo_cols, _mongo_doc_to_row, _mongo_oid, _parse_mongo_filter, _redis_rows


def get_data(ci, schema, table, page, size, where, order=""):
    size = max(1, min(int(size), 500))
    page = max(1, int(page))
    offset = (page - 1) * size
    if (ci.get("db_type") or "") == "mongodb":
        from dbcore import get_mongo
        client = get_mongo(ci)
        coll = client[schema][table]
        flt = _parse_mongo_filter(where)
        total = coll.count_documents(flt)
        cur = coll.find(flt)
        if order:
            col, _, d = order.partition(":")
            if d in ("asc", "desc"):
                cur = cur.sort(col, 1 if d == "asc" else -1)
        rows = [_mongo_doc_to_row(doc) for doc in cur.skip(offset).limit(size)]
        return {"columns": _mongo_cols(client, schema, table), "pk": ["_id"],
                "rows": rows, "total": total, "page": page, "size": size,
                "db_type": "mongodb"}
    if (ci.get("db_type") or "") == "redis":
        from dbcore import get_redis
        r = get_redis(ci)
        cols, rows, total = _redis_rows(r, table, size)
        return {"columns": cols, "pk": ["_id"], "rows": rows, "total": total,
                "page": page, "size": size, "db_type": "redis"}
    cols = get_columns(ci, schema, table)
    col_names = [c["name"] for c in cols]
    pk = get_pk(ci, schema, table)
    t = get_table_obj(ci, schema, table)
    w = safe_where_clause(where, col_names)
    where_clause = text(w) if w.strip() else sa_true()
    SKIP_ORDER = ("text", "ntext", "image", "xml", "clob", "blob", "json",
                  "longtext", "mediumtext", "tinytext", "character varying",
                  "varchar", "nvarchar")
    with get_engine(ci).connect() as conn:
        # count 缓存(60s TTL): 避免每次翻页都对大表全量 count
        count_key = _meta_key("cnt", conn_hash(ci), schema, table, w)
        total = _meta_get(count_key)
        if total is None:
            try:
                total = conn.execute(select(func.count()).select_from(t).where(where_clause)).scalar() or 0
                _meta_set(count_key, total)
            except Exception:
                total = -1  # count 超时/失败: 数据照常返回, 前端显示"总数未知"并禁用翻页
        stmt = select(t).where(where_clause)
        ob = []
        if order:
            # 显式排序: "列名:asc|desc" (已由路由校验格式)
            col_name, _, d = order.partition(":")
            if col_name in col_names and d in ("asc", "desc"):
                ob = [getattr(t.c[col_name], d)()]
        if not ob:
            ob = [t.c[p] for p in pk]
        if not ob:
            for c in cols:
                if c["type"].lower() in SKIP_ORDER:
                    continue
                if c.get("max_length") in (-1,):
                    continue
                ob.append(t.c[c["name"]])
                break
        if ob:
            stmt = stmt.order_by(*ob)
        stmt = stmt.limit(size).offset(offset)
        result = conn.execute(stmt)
        rows = [{k: py_to_json(v) for k, v in rec.items()}
                for rec in result.mappings()]
    return {"columns": cols, "pk": pk, "rows": rows, "total": total,
            "page": page, "size": size}

def mutate(ci, method, schema, table, body, use_tx=False, tx_key=""):
    if (ci.get("db_type") or "") == "mongodb":
        from dbcore import get_mongo
        coll = get_mongo(ci)[schema][table]
        orig = body.get("orig", {}) or {}
        values = body.get("values", {}) or {}
        if method == "POST":
            doc = {k: v for k, v in values.items() if k != "_id" or not v}
            r = coll.insert_one(doc)
            return {"ok": True, "affected": 1, "inserted_id": str(r.inserted_id)}
        if method == "DELETE":
            q = {}
            if orig.get("_id"):
                q["_id"] = _mongo_oid(orig["_id"])
            r = coll.delete_many(q)
            return {"ok": True, "affected": r.deleted_count}
        # PUT 更新: 用 orig._id 定位
        if not orig.get("_id"):
            raise ValueError("缺少 _id, 无法定位文档")
        q = {"_id": _mongo_oid(orig["_id"])}
        upd = {k: v for k, v in values.items() if k != "_id"}
        r = coll.update_one(q, {"$set": upd})
        return {"ok": True, "affected": r.modified_count}
    if (ci.get("db_type") or "") == "redis":
        from dbcore import get_redis
        r = get_redis(ci)
        t = r.type(table)
        orig = body.get("orig", {}) or {}
        values = body.get("values", {}) or {}
        if method == "DELETE":
            return {"ok": True, "affected": r.delete(table)}
        if method == "PUT":
            if t == "string":
                r.set(table, str(values.get("value", "")))
                return {"ok": True, "affected": 1}
            if t == "hash":
                fld = values.get("field") or (orig or {}).get("field")
                if fld is None:
                    raise ValueError("hash 更新缺少 field")
                r.hset(table, str(fld), str(values.get("value", "")))
                return {"ok": True, "affected": 1}
            if t == "list":
                idx = values.get("index")
                if idx is None:
                    raise ValueError("list 更新缺少 index")
                r.lset(table, int(idx), str(values.get("value", "")))
                return {"ok": True, "affected": 1}
            if t == "zset":
                mem = values.get("member") or (orig or {}).get("member")
                if mem is None:
                    raise ValueError("zset 更新缺少 member")
                r.zadd(table, {str(mem): float(values.get("score", 0))})
                return {"ok": True, "affected": 1}
            if t == "set":
                raise ValueError("Set 结构不支持单元格编辑，请删除后重建或使用命令行")
            raise ValueError("不支持的类型: " + t)
        raise ValueError("Redis 不支持该操作")
    pk = get_pk(ci, schema, table)
    cols = get_columns(ci, schema, table)
    colmap = {c["name"]: c for c in cols}
    orig = body.get("orig", {}) or {}
    values = body.get("values", {}) or {}
    def to_param(col_name, val):
        col = colmap.get(col_name, {})
        if val is None:
            return None
        if isinstance(val, str):
            s = val.strip()
            if s == "" and col.get("nullable", True):
                return None
            return s
        return val
    t = get_table_obj(ci, schema, table)
    engine = get_engine(ci)
    if method == "POST":
        ins = {k: to_param(k, v) for k, v in values.items()
               if k in colmap and not colmap[k]["identity"] and not colmap[k]["computed"]}
        if not ins:
            raise ValueError("没有可插入的有效字段")
        stmt = insert(t).values(**ins)
    else:
        if pk:
            where_cols = pk
            where_vals = [orig.get(p) for p in pk]
        else:
            where_cols = [c["name"] for c in cols]
            where_vals = [orig.get(c["name"]) for c in cols]
        conds = []
        for wc, wv in zip(where_cols, where_vals):
            conds.append(t.c[wc] == None if wv is None else t.c[wc] == wv)
        wc_expr = and_(*conds) if conds else sa_true()
        if method == "PUT":
            upd = {k: to_param(k, v) for k, v in values.items()
                   if k in colmap and k not in pk and not colmap[k]["identity"]
                   and not colmap[k]["computed"]}
            if not upd:
                raise ValueError("没有可更新的字段")
            stmt = update(t).where(wc_expr).values(**upd)
        else:  # DELETE
            stmt = delete(t).where(wc_expr)
    if use_tx:
        conn = get_connection(ci, use_tx=True, tx_key=tx_key)
        r = conn.execute(stmt)
        affected = r.rowcount
    else:
        with engine.connect() as conn:
            r = conn.execute(stmt)
            affected = r.rowcount
            conn.commit()  # 必须在连接关闭前提交, 否则事务随连接关闭回滚
    _clear_count_cache(conn_hash(ci), schema, table)
    return {"ok": True, "affected": affected}

def commit_transaction(ci, tx_key=""):
    key = (conn_hash(ci), tx_key or "")
    with LOCK:
        item = TX_CONN.get(key)
        if item:
            conn = item[0]
            try:
                conn.commit()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            TX_CONN.pop(key, None)
            return True
    return False

def rollback_transaction(ci, tx_key=""):
    key = (conn_hash(ci), tx_key or "")
    with LOCK:
        item = TX_CONN.get(key)
        if item:
            conn = item[0]
            try:
                conn.rollback()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            TX_CONN.pop(key, None)
            return True
    return False

