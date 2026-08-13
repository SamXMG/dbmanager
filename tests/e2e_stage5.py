# -*- coding: utf-8 -*-
"""阶段5 四项功能端到端: 表设计器(alter)/ER 图/数据同步(transfer)/结构同步(sync)
覆盖后端 /api/alter、/api/er、/api/transfer、/api/sync 链路(前端组件调同一批接口)"""
import json
import urllib.request
import urllib.error
import sqlite3
import os
import time
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlitedb   # 用于备份/恢复用户数据(改密流程影响同服务连跑的后续 e2e)

BASE = 'http://127.0.0.1:8770'
TAG = str(int(time.time()))
SRC = 'dbm_st5_src_%s.db' % TAG   # 项目根相对路径(P0-3 沙箱: 仅允许 cwd/DATA_ROOT 内)
DST = 'dbm_st5_dst_%s.db' % TAG
PASS, FAIL = [], []

def check(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print(('PASS' if cond else 'FAIL') + ' ' + name + (' | ' + extra if extra else ''))

def req(method, path, obj=None, tok=None, session=None):
    h = {'Content-Type': 'application/json'}
    if tok: h['X-User-Token'] = tok
    if session: h['X-Session'] = session
    data = json.dumps(obj).encode() if obj is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}

# 准备源库(带外键: dept <- emp) 与目标库(唯一文件名, 幂等建表, 避免服务引擎缓存句柄冲突)
c = sqlite3.connect(SRC)
c.execute('CREATE TABLE IF NOT EXISTS dept (id INTEGER PRIMARY KEY, name TEXT)')
c.execute('DELETE FROM dept')
c.execute("INSERT INTO dept (name) VALUES ('研发')")
c.execute("INSERT INTO dept (name) VALUES ('销售')")
c.execute('CREATE TABLE IF NOT EXISTS emp (id INTEGER PRIMARY KEY, name TEXT, dept_id INTEGER, FOREIGN KEY(dept_id) REFERENCES dept(id))')
c.execute('DELETE FROM emp')
c.execute("INSERT INTO emp (name, dept_id) VALUES ('张三', 1)")
c.execute("INSERT INTO emp (name, dept_id) VALUES ('李四', 2)")
c.commit(); c.close()
c = sqlite3.connect(DST)
c.execute('CREATE TABLE IF NOT EXISTS emp (id INTEGER PRIMARY KEY, name TEXT, dept_id INTEGER)')
c.execute('DELETE FROM emp')
c.commit(); c.close()

ADM_PWD = os.environ.get('DBM_DEFAULT_PWD') or 'admin123'
# 备份用户数据: 改密流程(must_change_pwd)会改 admin 口令, 结尾恢复以免影响同服务连跑的后续 e2e
_USERS_BAK = sqlitedb.users_load()
st, d = req('POST', '/api/login', {'username': 'admin', 'password': ADM_PWD})
tok = d.get('token', '')
# 强制改密(P0-1)适配: 非默认口令起库时 admin 首登须改密, 否则业务接口 403
if d.get('must_change_pwd'):
    st2, _ = req('POST', '/api/password', {'old_password': ADM_PWD, 'new_password': 'E2eAdmin@2026'}, tok=tok)
    check('admin 首次改密', st2 == 200, str(st2))

check('admin 登录', st == 200 and tok, str(st))
st, d = req('POST', '/api/connect', {'db_type': 'sqlite', 'database': SRC}, tok=tok)
check('连接源库', st == 200 and d.get('ok'), str(st))
ss = d.get('session', '')

# ---- 1 表设计器: SQLite 后端拒绝可视化 DDL(前端已适配: 只读展示 + 提示) ----
st, d = req('POST', '/api/alter', {'s': 'main', 't': 'emp', 'action': 'add_column',
                                   'payload': {'name': 'remark', 'type': 'TEXT', 'nullable': True, 'default': ''}}, tok=tok, session=ss)
check('sqlite alter 明确拒绝(500)', st == 500 and (d.get('error') or '').find('SQLite 暂不支持') >= 0, str(st) + ' ' + str(d)[:120])

# ---- 2 ER 图: /api/er ----
st, d = req('GET', '/api/er?s=main&t=emp', tok=tok, session=ss)
tables = d.get('tables') or []
rels = d.get('relations') or []
check('ER tables>=2', st == 200 and len(tables) >= 2, str(len(tables)))
check('ER 含 emp+dept', any(t.get('name') == 'emp' for t in tables) and any(t.get('name') == 'dept' for t in tables))
check('ER 关系含外键', any(r.get('from_table') == 'emp' and r.get('to_table') == 'dept' for r in rels), str(rels)[:150])
emp = next((t for t in tables if t.get('name') == 'emp'), {})
check('ER 表带列与 pk', len(emp.get('columns') or []) >= 3 and 'id' in (emp.get('pk') or []), str(emp)[:120])

# ---- 3 数据同步: /api/transfer(SQLite 跨库 = 目标文件路径) ----
st, d = req('POST', '/api/transfer', {'s': 'main', 't': 'emp', 'to_db': DST, 'to_t': 'emp'}, tok=tok, session=ss)
check('transfer 同步 2 行', st == 200 and d.get('transferred') == 2, str(d)[:120])
c = sqlite3.connect(DST)
cnt = c.execute('SELECT COUNT(*) FROM emp').fetchone()[0]
c.close()
check('目标库 emp=2', cnt == 2, str(cnt))

# ---- 4 结构同步: /api/sync(数据级: 同名列复制, replace=清空目标后复制) ----
dst_conn = {'db_type': 'sqlite', 'database': DST}
src_conn = {'db_type': 'sqlite', 'database': SRC}
st, d = req('POST', '/api/sync', {'src': src_conn, 'dst': dst_conn, 'schema': 'main', 'table': 'emp', 'mode': 'replace'}, tok=tok, session=ss)
check('sync replace 同步 2 行', st == 200 and d.get('synced') == 2, str(d)[:150])
c = sqlite3.connect(DST)
cnt2 = c.execute('SELECT COUNT(*) FROM emp').fetchone()[0]
c.close()
check('目标库 emp=2(replace 清空后)', cnt2 == 2, str(cnt2))


# 恢复原始用户数据(防影响同服务连跑的后续 e2e)
if _USERS_BAK is not None:
    sqlitedb.users_save(_USERS_BAK)
print('\n===== 阶段5 四项端到端: %d PASS / %d FAIL =====' % (len(PASS), len(FAIL)))
if FAIL:
    print('失败项:', FAIL)
    raise SystemExit(1)
