# -*- coding: utf-8 -*-
"""简单调度器(P2-2): 任务存 SQLite(tasks 表, 旧 tasks.json 自动迁移) + 后台线程循环检查 + 定时备份
任务字段: id, name, action('backup'), conn_name(引用已保存连接, 不存密码),
         interval_min(间隔分钟), enabled, last_run, next_run, last_result
备份输出: backups/backup_{name}_{YYYYmmdd_HHMMSS}.sql
启动: app.py 中调用 start() 起 daemon 线程, 每 15s 检查一次
"""
import os
import threading
import time
from datetime import datetime

import sqlitedb

_BASE = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(_BASE, 'tasks.json')   # 遗留路径: 仅迁移检测
BACKUP_DIR = os.path.join(_BASE, 'backups')
LOCK = threading.Lock()
_seq = [0]


def _load() -> list:
    if os.path.exists(TASKS_FILE):
        sqlitedb.migrate_tasks_json(TASKS_FILE)
    return sqlitedb.tasks_load()


def _save(tasks: list) -> None:
    with LOCK:
        sqlitedb.tasks_save(tasks)


def _new_id(tasks: list) -> int:
    _seq[0] = max([t.get('id', 0) for t in tasks] or [0]) + 1
    return _seq[0]


def list_tasks() -> list:
    return _load()


def add_task(name: str, conn_name: str, interval_min: int,
             action: str = 'backup', enabled: bool = True) -> dict:
    tasks = _load()
    interval = max(1, int(interval_min or 1))
    t = {'id': _new_id(tasks), 'name': name, 'action': action,
         'conn_name': conn_name, 'interval_min': interval,
         'enabled': bool(enabled), 'last_run': None, 'last_result': None,
         'next_run': time.time() + interval * 60}
    tasks.append(t)
    _save(tasks)
    return t


def delete_task(tid: int) -> bool:
    tasks = [t for t in _load() if t.get('id') != tid]
    _save(tasks)
    return True


def toggle_task(tid: int, enabled: bool) -> bool:
    tasks = _load()
    for t in tasks:
        if t.get('id') == tid:
            t['enabled'] = bool(enabled)
            if enabled:
                t['next_run'] = time.time() + t.get('interval_min', 60) * 60
    _save(tasks)
    return True


def _run_backup(task: dict) -> dict:
    """执行备份任务: 按连接名取配置(含解密密码) -> 生成 SQL 脚本写 backups/"""
    from store import get_connection_by_name
    from ops import backup_database
    conn = get_connection_by_name(task.get('conn_name', ''))
    if not conn:
        return {'error': '连接不存在或已删除'}
    try:
        content, _fn = backup_database(conn, None)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        safe = ''.join(c for c in str(task.get('name', 'task')) if c.isalnum() or c in '-_') or 'task'
        fn = 'backup_%s_%s.sql' % (safe, datetime.now().strftime('%Y%m%d_%H%M%S'))
        with open(os.path.join(BACKUP_DIR, fn), 'w', encoding='utf-8') as f:
            f.write(content)
        return {'ok': True, 'file': fn}
    except Exception as e:
        return {'error': str(e)}


def run_now(tid: int) -> dict:
    """手动立即执行一次(调试/用户主动触发)"""
    tasks = _load()
    task = next((t for t in tasks if t.get('id') == tid), None)
    if not task:
        return {'error': '任务不存在'}
    r = _run_backup(task)
    now = time.time()
    for t in tasks:
        if t.get('id') == tid:
            t['last_run'] = now
            t['last_result'] = 'ok' if r.get('ok') else ('err: ' + str(r.get('error'))[:50])
            t['next_run'] = now + t.get('interval_min', 60) * 60
    _save(tasks)
    return r


def _tick() -> None:
    now = time.time()
    tasks = _load()
    for t in tasks:
        if not t.get('enabled'):
            continue
        if t.get('next_run') and t['next_run'] <= now:
            r = _run_backup(t)
            tasks = _load()  # 执行期间可能被 API 修改, 重新读
            for x in tasks:
                if x.get('id') == t.get('id'):
                    x['last_run'] = now
                    x['last_result'] = 'ok' if r.get('ok') else ('err: ' + str(r.get('error'))[:60])
                    x['next_run'] = now + x.get('interval_min', 60) * 60
            _save(tasks)


def start() -> None:
    """启动调度线程(app.py run 时调用)"""
    def loop():
        while True:
            try:
                _tick()
            except Exception:
                pass
            time.sleep(15)
    threading.Thread(target=loop, daemon=True).start()
