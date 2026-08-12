# -*- coding: utf-8 -*-
"""dbmanager - ops 非SQL库(MongoDB/Redis) 数据形态转换与查询安全"""
import json

def _mongo_doc_to_row(doc):
    """文档展平为行: _id 转字符串, 嵌套 dict/list 转 JSON 文本"""
    row = {}
    for k, v in doc.items():
        if k == "_id":
            row["_id"] = str(v)
        elif isinstance(v, (dict, list)):
            row[k] = json.dumps(v, ensure_ascii=False, default=str)
        else:
            row[k] = v
    return row


def _mongo_cols(client, db, coll, sample=100):
    """采样文档提取列集合(键并集, _id 放首位)"""
    names = []
    seen = set()
    try:
        for doc in client[db][coll].find({}, limit=sample):
            for k in doc:
                if k not in seen:
                    seen.add(k)
                    names.append(k)
    except Exception:
        pass
    if "_id" in seen:
        names.remove("_id")
        names.insert(0, "_id")
    return [{"name": n, "type": "mixed"} for n in names]


def _mongo_oid(v):
    """把 _id 字符串转 ObjectId(失败则原样)"""
    try:
        from bson import ObjectId
        return ObjectId(str(v))
    except Exception:
        return v


# ------------------------------
# Redis: KV 结构, 键即"表"; string/hash/list/set/zset 五类结构转表格展示
# ------------------------------
REDIS_TYPE_LABEL = {"string": "String", "hash": "Hash", "list": "List",
                    "set": "Set", "zset": "ZSet", "none": "Key"}


def _redis_type_label(t):
    return REDIS_TYPE_LABEL.get(t or "", "Key")


def _redis_rows(r, key, limit=500):
    """按结构类型取内容为表格行, 返回 (columns, rows, total)"""
    t = r.type(key)
    if t == "string":
        return [{"name": "value"}], [{"value": r.get(key) or ""}], 1
    if t == "hash":
        data = r.hgetall(key)
        items = list(data.items())[:limit]
        return [{"name": "field"}, {"name": "value"}], \
               [{"field": f, "value": v} for f, v in items], len(data)
    if t == "list":
        vals = r.lrange(key, 0, limit - 1)
        return [{"name": "index"}, {"name": "value"}], \
               [{"index": i, "value": v} for i, v in enumerate(vals)], r.llen(key)
    if t == "set":
        vals = sorted(r.smembers(key))[:limit]
        return [{"name": "value"}], [{"value": v} for v in vals], r.scard(key)
    if t == "zset":
        vals = r.zrange(key, 0, limit - 1, withscores=True)
        return [{"name": "member"}, {"name": "score"}], \
               [{"member": m, "score": s} for m, s in vals], r.zcard(key)
    return [{"name": "value"}], [{"value": "(空)"}], 0


# MongoDB: 查询条件解析与安全校验(拒绝执行 JS 的操作符)
_MONGO_BLOCKED_OPS = ("$where", "$function", "$accumulator")


def _parse_mongo_filter(where):
    """where 参数(JSON 对象字符串) -> find 条件 dict; 空/非 JSON 返回 {}"""
    s = (where or "").strip()
    if not s:
        return {}
    if not s.startswith("{"):
        raise ValueError("MongoDB 查询请输入 JSON 条件，如 {\"age\": {\"$gt\": 30}}")
    try:
        flt = json.loads(s)
    except Exception:
        raise ValueError("JSON 解析失败: " + s[:80])
    if not isinstance(flt, dict):
        raise ValueError("查询条件必须是 JSON 对象，如 {\"name\": \"张三\"}")
    _reject_mongo_ops(flt)
    return flt


def _reject_mongo_ops(node, depth=0):
    """递归检查并拒绝可执行 JS 的查询操作符"""
    if depth > 12:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _MONGO_BLOCKED_OPS:
                raise ValueError("查询包含不安全的操作符: " + k)
            _reject_mongo_ops(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _reject_mongo_ops(v, depth + 1)

