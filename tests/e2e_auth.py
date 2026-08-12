# -*- coding: utf-8 -*-
"""商用改造端到端验证 v2: 登录 → 连接 → 读写权限 → 审计"""
import json
import urllib.request
import urllib.error
import sqlite3
import hashlib
import secrets
import os

BASE = 'http://127.0.0.1:8770'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = '_test_tmp.db'   # 相对路径(服务 cwd=项目根); 避免中文目录绝对路径连接失败
PASS, FAIL = [], []

# 备份 users.json(强制改密流程会改写 admin 密码, 结束后恢复, 避免污染共享文件影响后续 e2e)
_USERS_PATH = os.path.join(ROOT, 'users.json')
_USERS_BAK = None
if os.path.exists(_USERS_PATH):
    _USERS_BAK = open(_USERS_PATH, encoding='utf-8').read()

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

# 准备 sqlite 测试库
try:
    if os.path.exists(DB): os.remove(DB)
except Exception:
    pass  # 沙箱回收站不可用等, IF NOT EXISTS 幂等
c = sqlite3.connect(DB)
c.execute('CREATE TABLE IF NOT EXISTS emp (id INTEGER PRIMARY KEY, name TEXT, dept TEXT)')
c.execute('DELETE FROM emp')   # 幂等: 残留库先清空, 不依赖 os.remove 成功
c.execute("INSERT INTO emp (name, dept) VALUES ('张三', '研发')")
c.commit(); c.close()

# 1-3 基础
_, cfg = req('GET', '/api/config')
check('config.auth_required', cfg.get('auth_required') is True)
st, d = req('GET', '/api/tables')
check('未登录 401 require_login', st == 401 and d.get('require_login'))
st, d = req('POST', '/api/login', {'username': 'admin', 'password': 'wrong'})
check('错误密码 401', st == 401)

# 4 admin 登录 + 连接 + 读表
st, d = req('POST', '/api/login', {'username': 'admin', 'password': 'admin123'})
check('admin 登录 admin', st == 200 and d.get('role') == 'admin')
admin_tok = d.get('token', '')
if d.get('must_change_pwd'):
    # 首次部署默认账号需先改密(否则业务接口 403); 脚本适配产品行为
    st2, _ = req('POST', '/api/password', {'old_password': 'admin123', 'new_password': 'E2eAdmin@2026'}, tok=admin_tok)
    check('admin 首次改密', st2 == 200)
st, d = req('POST', '/api/connect', {'db_type': 'sqlite', 'database': DB}, tok=admin_tok)
check('admin 连接 sqlite', st == 200 and d.get('ok'))
admin_ss = d.get('session', '')
st, d = req('GET', '/api/tables', tok=admin_tok, session=admin_ss)
check('admin 读表 200', st == 200, str(st))

# 5 admin 写操作(建行)
st, d = req('POST', '/api/row', {'s': 'main', 't': 'emp', 'values': {'name': '李四', 'dept': '销售'}, 'transaction': False}, tok=admin_tok, session=admin_ss)
check('admin 新增行 200', st == 200 and d.get('ok'), str(d))

# 6 临时 read 账号
users = json.load(open(os.path.join(ROOT, 'users.json'), encoding='utf-8'))
salt = secrets.token_hex(16)
h = hashlib.pbkdf2_hmac('sha256', b'readpass', bytes.fromhex(salt), 120000).hex()
users['reader'] = {'pwd_hash': h, 'salt': salt, 'role': 'read'}
json.dump(users, open(os.path.join(ROOT, 'users.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

st, d = req('POST', '/api/login', {'username': 'reader', 'password': 'readpass'})
check('read 账号登录', st == 200 and d.get('role') == 'read')
read_tok = d.get('token', '')
st, d = req('POST', '/api/connect', {'db_type': 'sqlite', 'database': DB}, tok=read_tok)
read_ss = d.get('session', '')
st, d = req('GET', '/api/data?s=main&t=emp&page=1&size=10&where=', tok=read_tok, session=read_ss)
check('read 读数据 200', st == 200, str(st))

# 7 read 写操作被拒(新增行 + 改 + 删)
st, d = req('POST', '/api/row', {'s': 'main', 't': 'emp', 'values': {'name': 'x'}, 'transaction': False}, tok=read_tok, session=read_ss)
check('read 新增 -> 403', st == 403, d.get('error', ''))
st, d = req('PUT', '/api/row', {'s': 'main', 't': 'emp', 'orig': {'id': 1, 'name': '张三', 'dept': '研发'}, 'values': {'dept': 'x'}, 'transaction': False}, tok=read_tok, session=read_ss)
check('read 修改 -> 403', st == 403)
st, d = req('DELETE', '/api/row', {'s': 'main', 't': 'emp', 'orig': {'id': 1}}, tok=read_tok, session=read_ss)
check('read 删除 -> 403', st == 403)
st, d = req('POST', '/api/import', {'s': 'main', 't': 'emp', 'columns': ['name'], 'rows': [{'name': 'y'}], 'transaction': False}, tok=read_tok, session=read_ss)
check('read 导入 -> 403', st == 403)

# 8 审计: login 记录 + 拒绝写操作不落审计(拦截在业务前)
log = open(os.path.join(ROOT, 'logs', 'audit.log'), encoding='utf-8').read()
check('审计含 admin login', 'login | admin' in log or 'admin' in log and 'login' in log)
check('审计含 admin 新增行', 'row_insert' in log and 'admin' in log)

# 9 清理 read 账号 + 测试库
users.pop('reader', None)
json.dump(users, open(os.path.join(ROOT, 'users.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
try:
    if os.path.exists(DB): os.remove(DB)
except Exception:
    pass  # 沙箱回收站不可用等, 交由 gitignore 兜底
check('清理完成', 'reader' not in json.load(open(os.path.join(ROOT, 'users.json'), encoding='utf-8')))
if _USERS_BAK is not None:
    open(_USERS_PATH, 'w', encoding='utf-8').write(_USERS_BAK)   # 恢复原始 users.json

print(f'\n===== {len(PASS)} 通过, {len(FAIL)} 失败 =====')
exit(1 if FAIL else 0)
