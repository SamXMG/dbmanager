# -*- coding: utf-8 -*-
"""阶段5 批2-6 新功能端到端: DB用户路由/备份还原/测试数据/事务链路/gen-data/schema-diff/routine 接口"""
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
DB = 'dbm_st5b_%s.db' % int(time.time())   # 项目根相对路径(P0-3 沙箱)
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
            return resp.status, body
        return resp.status, json.loads(body.decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}

c = sqlite3.connect(DB)
c.execute('CREATE TABLE IF NOT EXISTS emp (id INTEGER PRIMARY KEY, name TEXT, dept TEXT)')
c.execute('DELETE FROM emp')
c.execute("INSERT INTO emp (name, dept) VALUES ('张三', '研发')")
c.execute("INSERT INTO emp (name, dept) VALUES ('李四', '销售')")
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
st, d = req('POST', '/api/connect', {'db_type': 'sqlite', 'database': DB}, tok=tok)
check('连接', st == 200 and d.get('ok'), str(st))
ss = d.get('session', '')

# 1 DB 用户路由 /api/db-users(sqlite 应返回 supported=False)
st, d = req('GET', '/api/db-users', tok=tok, session=ss)
check('db-users 路由存在', st == 200 and d.get('supported') is False, str(st) + ' ' + str(d)[:80])

# 2 备份 /api/backup -> SQL 文本
st, body = req('GET', '/api/backup', tok=tok, session=ss, raw=True)
txt = body.decode('utf-8', errors='ignore')
check('backup 返回 SQL', st == 200 and 'CREATE TABLE' in txt and 'INSERT INTO' in txt, str(st) + ' len=' + str(len(txt)))

# 3 还原 /api/restore: 清空 emp -> 还原备份 -> 数据恢复
st, d = req('POST', '/api/sql', {'sql': 'DELETE FROM emp', 'write': True}, tok=tok, session=ss)
check('清空 emp', st == 200 and (d.get('results') or [{}])[0].get('ok') or d.get('ok'), str(d)[:80])
st, d = req('POST', '/api/restore', {'sql': txt}, tok=tok, session=ss)
check('restore 还原', st == 200 and not d.get('failed'), str(d)[:100])
st, d = req('POST', '/api/sql', {'sql': 'SELECT COUNT(*) AS n FROM emp'}, tok=tok, session=ss)
check('还原后 emp>=2', (d.get('results') or [{}])[0].get('rows', [{}])[0].get('n', 0) >= 2, str(d)[:80])

# 4 测试数据生成 /api/gen-data(追加 10 行)
st, d = req('POST', '/api/gen-data', {'s': 'main', 't': 'emp', 'rows': 10}, tok=tok, session=ss)
check('gen-data 生成 10 行', st == 200 and d.get('inserted') == 10, str(d)[:100])

# 5 事务链路: transaction=true 开启 -> rollback 不落库 -> 再开 -> commit 落库
st, d = req('POST', '/api/row', {'s': 'main', 't': 'emp', 'values': {'name': '事务测试', 'dept': 'QA'}, 'transaction': True, 'tx_id': 'e2e-tx1'}, tok=tok, session=ss)
check('事务 insert ok', st == 200 and d.get('ok'), str(d)[:100])
st, d = req('POST', '/api/transaction/rollback', {'tx_id': 'e2e-tx1'}, tok=tok, session=ss)
check('rollback ok', st == 200, str(st))
st, d = req('POST', '/api/sql', {'sql': "SELECT COUNT(*) AS n FROM emp WHERE name='事务测试'"}, tok=tok, session=ss)
check('rollback 后不落库', (d.get('results') or [{}])[0].get('rows', [{}])[0].get('n', 1) == 0, str(d)[:80])
st, d = req('POST', '/api/row', {'s': 'main', 't': 'emp', 'values': {'name': '事务测试2', 'dept': 'QA'}, 'transaction': True, 'tx_id': 'e2e-tx2'}, tok=tok, session=ss)
st, d = req('POST', '/api/transaction/commit', {'tx_id': 'e2e-tx2'}, tok=tok, session=ss)
check('commit ok', st == 200, str(st))
st, d = req('POST', '/api/sql', {'sql': "SELECT COUNT(*) AS n FROM emp WHERE name='事务测试2'"}, tok=tok, session=ss)
check('commit 后落库=1', (d.get('results') or [{}])[0].get('rows', [{}])[0].get('n', 0) == 1, str(d)[:80])

# 6 schema/diff 跨连接(sqlite 支持与否看返回, 至少路由通)
st, d = req('POST', '/api/schema/diff', {'src': {'db_type': 'sqlite', 'database': DB}, 'dst': {'db_type': 'sqlite', 'database': DB}, 'schema': 'main', 'table': 'emp'}, tok=tok, session=ss)
check('schema/diff 路由通', st == 200, str(st) + ' ' + str(d)[:100])

# 7 routine 接口(sqlite 无存储过程: save 执行必然报错返回 error, 前端 toast 提示)
st, d = req('POST', '/api/routine/save', {'s': 'main', 'name': 'p1', 'kind': 'Procedure', 'source': 'x'}, tok=tok, session=ss)
check('routine/save 返回 error', st in (200, 500) and 'error' in d, str(st) + ' ' + str(d)[:120])
st, d = req('GET', '/api/routine/source?s=main&name=p1&kind=Procedure', tok=tok, session=ss)
check('routine/source 路由通', st == 200, str(st))


# 恢复原始用户数据(防影响同服务连跑的后续 e2e)
if _USERS_BAK is not None:
    sqlitedb.users_save(_USERS_BAK)
print('\n===== 批2-6 端到端: %d PASS / %d FAIL =====' % (len(PASS), len(FAIL)))
if FAIL:
    print('失败项:', FAIL)
    raise SystemExit(1)
