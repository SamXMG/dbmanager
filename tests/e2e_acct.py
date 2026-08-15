# -*- coding: utf-8 -*-
"""账号功能端到端 v2: 限流(独立用户名) / 改密 / 账号管理(独立 write 账号)"""
import json
import os
import urllib.request
import urllib.error
import hashlib
import secrets

BASE = 'http://127.0.0.1:8770'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS, FAIL = [], []

def check(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print(('PASS' if cond else 'FAIL') + ' ' + name + (' | ' + extra if extra else ''))

def req(method, path, obj=None, tok=None):
    h = {'Content-Type': 'application/json'}
    if tok: h['X-User-Token'] = tok
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

def mkuser(name, pwd, role):
    salt = secrets.token_hex(16)
    return {'pwd_hash': hashlib.pbkdf2_hmac('sha256', pwd.encode(), bytes.fromhex(salt), 120000).hex(), 'salt': salt, 'role': role}

import sys
sys.path.insert(0, ROOT)
from db import sqlitedb
users = sqlitedb.users_load()
# 备份原始, 注入测试账号
BACKUP = json.loads(json.dumps(users))
users.update({
    'victim': mkuser('victim', 'victim123', 'write'),   # 用于限流测试(独立 key)
    'reader2': mkuser('reader2', 'readpass', 'read'),
    'mgr': mkuser('mgr', 'mgr123', 'admin'),   # 账号管理需 admin 角色(37ad19f 后 _require_admin)
})
sqlitedb.users_save(users)

# === 1. 限流: victim 连续 6 次错误 ===
codes = [req('POST', '/api/login', {'username': 'victim', 'password': 'x%d' % i})[0] for i in range(6)]
check('victim 第 6 次失败 429 锁定', codes[-1] == 429, 'codes=' + str(codes))
st, d = req('POST', '/api/login', {'username': 'victim', 'password': 'victim123'})
check('锁定期间正确密码也 429', st == 429, str(st))
# 其他用户名不受影响(不同 key)
st, _ = req('POST', '/api/login', {'username': 'mgr', 'password': 'mgr123'})
check('其他用户不受限流影响', st == 200, str(st))

# === 2. 改密(reader2) ===
st, d = req('POST', '/api/login', {'username': 'reader2', 'password': 'readpass'})
check('reader2 登录', st == 200)
rt = d.get('token', '')
st, d = req('POST', '/api/password', {'old_password': 'wrong', 'new_password': 'newpass1'}, tok=rt)
check('旧密码错误 -> 400', st == 400, d.get('error', ''))
st, d = req('POST', '/api/password', {'old_password': 'readpass', 'new_password': 'newpass1'}, tok=rt)
check('改密成功 -> 200', st == 200, d.get('message', ''))
st, d = req('POST', '/api/login', {'username': 'reader2', 'password': 'newpass1'})
check('新密码可登录', st == 200)

# === 3. 账号管理权限: read 账号访问 -> 403 ===
rt2 = d.get('token', '')
st, d = req('GET', '/api/users', tok=rt2)
check('read 账号访问账号列表 -> 403', st == 403, str(st))
st, d = req('POST', '/api/users', {'username': 'hack', 'role': 'write', 'password': 'hack123'}, tok=rt2)
check('read 账号建账号 -> 403', st == 403)

# === 4. 账号管理(admin 账号 mgr) ===
st, d = req('POST', '/api/login', {'username': 'mgr', 'password': 'mgr123'})
mt = d.get('token', '')
st, d = req('GET', '/api/users', tok=mt)
names = [u['username'] for u in d.get('users', [])]
check('mgr 列表账号 200', st == 200 and 'mgr' in names and 'admin' in names, str(names))
# 新建账号
st, d = req('POST', '/api/users', {'username': 'newbie', 'role': 'read', 'password': 'newbie123'}, tok=mt)
check('新建账号 200', st == 200, d.get('message', ''))
# 新账号可登录
st, d = req('POST', '/api/login', {'username': 'newbie', 'password': 'newbie123'})
check('新账号登录成功', st == 200)
# 改角色(read -> write)
st, d = req('POST', '/api/users', {'username': 'newbie', 'role': 'write'}, tok=mt)
check('改角色 200', st == 200)
# 重置密码(保留角色): 读回确认角色仍是 write
st, d = req('POST', '/api/users', {'username': 'newbie', 'password': 'changed123'}, tok=mt)
check('重置密码 200', st == 200)
st, d = req('GET', '/api/users', tok=mt)
nb = next((u for u in d.get('users', []) if u['username'] == 'newbie'), None)
check('重置密码后角色保留 write', nb is not None and nb['role'] == 'write', str(nb))
# 删除账号(不能删自己)
st, d = req('POST', '/api/users/delete', {'username': 'mgr'}, tok=mt)
check('不能删除自己 -> 400', st == 400, d.get('error', ''))
st, d = req('POST', '/api/users/delete', {'username': 'newbie'}, tok=mt)
check('删除他人账号 200', st == 200)
# 删除后登录失败
st, _ = req('POST', '/api/login', {'username': 'newbie', 'password': 'changed123'})
check('删除后无法登录', st == 401)

# === 5. 恢复用户数据 ===
sqlitedb.users_save(BACKUP)
restored = sqlitedb.users_load()
check('用户数据已恢复', set(restored.keys()) == set(BACKUP.keys()) and 'mgr' not in restored)

print(f'\n===== {len(PASS)} 通过, {len(FAIL)} 失败 =====')
exit(1 if FAIL else 0)
