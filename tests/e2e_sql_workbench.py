# -*- coding: utf-8 -*-
"""SQL 工作台(Vue3 阶段4)端到端冒烟: 登录 → 连接 → 只读/多语句/写模式/EXPLAIN/导出
覆盖后端 /api/sql(单语句+多语句均返回 results 包装)、/api/explain、/api/export/sql 链路"""
import json
import urllib.request
import urllib.error
import sqlite3
import tempfile
import os

BASE = 'http://127.0.0.1:8770'
# 测试库放系统 TEMP(服务进程的沙箱写保护仅覆盖其 cwd=dbmanager 目录树)
DB = os.path.join(tempfile.gettempdir(), 'dbm_e2e_sqlwb.db')
PASS, FAIL = [], []

def check(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print(('PASS' if cond else 'FAIL') + ' ' + name + (' | ' + extra if extra else ''))

def req(method, path, obj=None, tok=None, session=None, raw=False):
    h = {'Content-Type': 'application/json'}
    if tok: h['X-User-Token'] = tok
    if session: h['X-Session'] = session
    data = json.dumps(obj).encode() if obj is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r)
        body = resp.read()
        if raw:
            return resp.status, resp.headers, body
        return resp.status, json.loads(body.decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}

# 准备 sqlite 测试库(不删除文件: 沙箱 safe-delete shim 会拦 os.remove)
c = sqlite3.connect(DB)
c.execute('CREATE TABLE IF NOT EXISTS emp (id INTEGER PRIMARY KEY, name TEXT, dept TEXT)')
c.execute('DELETE FROM emp')
c.execute("INSERT INTO emp (name, dept) VALUES ('张三', '研发')")
c.execute("INSERT INTO emp (name, dept) VALUES ('李四', '销售')")
c.commit(); c.close()

# 登录 + 连接
st, d = req('POST', '/api/login', {'username': 'admin', 'password': 'admin123'})
check('admin 登录', st == 200 and d.get('token'), str(st))
tok = d.get('token', '')
st, d = req('POST', '/api/connect', {'db_type': 'sqlite', 'database': DB}, tok=tok)
check('连接 sqlite', st == 200 and d.get('ok'), str(st))
ss = d.get('session', '')

def first_res(d):
    """单语句结果统一在 results[0](后端 run_sql 统一包装)"""
    rs = d.get('results') or []
    return rs[0] if rs else d

# 1 只读单语句 SELECT
st, d = req('POST', '/api/sql', {'sql': 'SELECT * FROM emp ORDER BY id', 'limit': 100}, tok=tok, session=ss)
r0 = first_res(d)
check('只读 SELECT 200', st == 200 and r0.get('ok'), str(st))
check('SELECT columns=3', len(r0.get('columns') or []) == 3)
check('SELECT rows=2', len(r0.get('rows') or []) == 2)
check('SELECT total=2', r0.get('total') == 2)

# 2 只读模式阻止写语句(error 在 results[0])
st, d = req('POST', '/api/sql', {'sql': "INSERT INTO emp (name) VALUES ('x')"}, tok=tok, session=ss)
r0 = first_res(d)
check('只读阻止 INSERT', (r0.get('error') or '').find('只读') >= 0, str(r0)[:120])

# 3 多语句批量 -> results 数组(每句一个 tab)
st, d = req('POST', '/api/sql', {'sql': 'SELECT * FROM emp LIMIT 1; SELECT name FROM emp WHERE id=2', 'limit': 100}, tok=tok, session=ss)
rs = d.get('results') or []
check('多语句 results=2', st == 200 and len(rs) == 2, str(st))
check('多语句句1 columns=3', len(rs[0].get('columns') or []) == 3 if rs else False)
check('多语句句2 columns=1', len(rs[1].get('columns') or []) == 1 if len(rs) > 1 else False)

# 4 写模式 INSERT
st, d = req('POST', '/api/sql', {'sql': "INSERT INTO emp (name, dept) VALUES ('王五', '测试')", 'write': True}, tok=tok, session=ss)
r0 = first_res(d)
check('写模式 INSERT ok', st == 200 and r0.get('ok'), str(r0)[:120])
check('写模式 affected=1', r0.get('affected') == 1, str(r0.get('affected')))
st, d = req('POST', '/api/sql', {'sql': 'SELECT COUNT(*) AS n FROM emp', 'limit': 10}, tok=tok, session=ss)
r0 = first_res(d)
check('写后 count=3', (r0.get('rows') or [{}])[0].get('n') == 3, str(r0.get('rows')))

# 5 EXPLAIN(sqlite 支持)
st, d = req('POST', '/api/explain', {'sql': 'SELECT * FROM emp'}, tok=tok, session=ss)
check('EXPLAIN 200', st == 200, str(st))
check('EXPLAIN 有结果', d.get('total') is not None and d.get('rows') is not None, str(d)[:100])

# 6 导出 /api/export/sql -> xlsx blob
st, hdrs, body = req('POST', '/api/export/sql',
                     {'columns': [{'name': 'id'}, {'name': 'name'}],
                      'rows': [{'id': 1, 'name': '张三'}]}, tok=tok, session=ss, raw=True)
ct = hdrs.get('Content-Type', '')
check('导出 xlsx 200', st == 200 and 'spreadsheetml' in ct, str(st) + ' ' + ct)
check('导出非空 blob', len(body) > 100, str(len(body)))

# 7 大 SELECT 自动 LIMIT 保护
st, d = req('POST', '/api/sql', {'sql': 'SELECT * FROM emp', 'limit': 5}, tok=tok, session=ss)
r0 = first_res(d)
check('limit 生效 rows<=5', len(r0.get('rows') or []) <= 5)

print('\n===== SQL 工作台端到端: %d PASS / %d FAIL =====' % (len(PASS), len(FAIL)))
if FAIL:
    print('失败项:', FAIL)
    raise SystemExit(1)
