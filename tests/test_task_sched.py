# -*- coding: utf-8 -*-
"""P2-2 调度任务逻辑单测: 重定向 tasks 存储到 TEMP(本环境沙箱写保护 dbmanager 目录),
mock get_connection_by_name 返回临时 sqlite 库, 验证 增/查/执行备份/启停/删 全链路。
数据层已迁 SQLite: 必须把 DBM_DB_FILE 指到临时库, 防污染真实 dbmanager.db。
"""
import os
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 隔离数据层: 在 import task_sched 之前把 DBM_DB_FILE 指到临时库, 防测试污染真实 dbmanager.db
_TMP_ROOT = tempfile.mkdtemp(prefix="dbm_task_test_")
os.environ["DBM_DB_FILE"] = os.path.join(_TMP_ROOT, "dbmanager.db")

from core import config
import sqlite3
from infra import task_sched

# P0-3 沙箱适配: 测试库/备份目录在系统 TEMP, 追加为 SQLite 允许根(仅测试生效, 不削弱生产默认)
config.SQLITE_ALLOW_ROOTS = [tempfile.gettempdir()]

# 重定向备份目录到 TEMP(环境: 沙箱对项目根目录写保护)
TMP = tempfile.gettempdir()
task_sched.BACKUP_DIR = os.path.join(TMP, 'dbm_backups_test_%d' % int(time.time()))

DB = os.path.join(TMP, 'dbm_task_db_%d.db' % int(time.time()))
c = sqlite3.connect(DB)
c.execute('CREATE TABLE IF NOT EXISTS emp (id INTEGER PRIMARY KEY, name TEXT)')
c.execute('DELETE FROM emp')
c.execute("INSERT INTO emp (name) VALUES ('张三')")
c.commit(); c.close()

PASS, FAIL = [], []
def check(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print(('PASS' if cond else 'FAIL') + ' ' + name + (' | ' + extra if extra else ''))

# 1 新建任务
t = task_sched.add_task('unit_backup', 'fake_conn', 1)
check('add_task 返回 id', t.get('id') == 1 and t.get('enabled'), str(t))
check('next_run 已排程', t.get('next_run') and t.get('next_run') > time.time())

# 2 列表持久化(重读文件)
tasks = task_sched.list_tasks()
check('list_tasks 持久化', len(tasks) == 1 and tasks[0]['name'] == 'unit_backup', str(tasks))

# 3 手动执行备份(mock 连接名 -> 临时 sqlite)
fake_conn = {'db_type': 'sqlite', 'database': DB}
with patch('db.store.get_connection_by_name', return_value=fake_conn):
    r = task_sched.run_now(1)
check('run_now 备份 ok', r.get('ok') and r.get('file'), str(r)[:120])
check('备份文件生成', os.path.exists(os.path.join(task_sched.BACKUP_DIR, r.get('file', ''))), str(r))
with open(os.path.join(task_sched.BACKUP_DIR, r.get('file', '')), encoding='utf-8') as f:
    content = f.read()
check('备份内容含 CREATE TABLE', 'CREATE TABLE' in content, '')

# 4 执行后 last_run/last_result 更新
tasks = task_sched.list_tasks()
check('last_run 已记录', tasks[0].get('last_run') is not None and tasks[0].get('last_result') == 'ok', str(tasks[0]))

# 5 停用 -> 启用
task_sched.toggle_task(1, False)
check('toggle 停用', task_sched.list_tasks()[0].get('enabled') is False)
task_sched.toggle_task(1, True)
check('toggle 启用', task_sched.list_tasks()[0].get('enabled') is True)

# 6 删除
task_sched.delete_task(1)
check('delete 生效', len(task_sched.list_tasks()) == 0)

# 7 不存在的连接 -> 明确错误
t2 = task_sched.add_task('bad_conn', 'not_exist', 1)
with patch('db.store.get_connection_by_name', return_value=None):
    r = task_sched.run_now(t2['id'])
check('连接不存在返回错误', not r.get('ok') and '连接不存在' in str(r.get('error')), str(r)[:80])

print('\n===== P2-2 调度任务单测: %d PASS / %d FAIL =====' % (len(PASS), len(FAIL)))
if FAIL:
    print('失败项:', FAIL)
    raise SystemExit(1)
