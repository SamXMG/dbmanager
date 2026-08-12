# -*- coding: utf-8 -*-
"""dbmanager - 轻量进程指标(Prometheus 采集)
独立模块零依赖(仅标准库), handler.py 与 routes/monitor.py 共同引用, 避免循环导入。
- record(method, path, status): 请求结束回调, 线程安全计数
- uptime(): 进程存活秒数
"""
import threading
import time

METRICS = {
    "uptime_start": time.time(),
    "requests_total": 0,      # 总请求数
    "requests": {},           # (method, path) -> count
    "status_codes": {},       # status -> count
    "errors_total": 0,        # 5xx 计数
}
METRICS_LOCK = threading.Lock()


def record(method, path, status):
    """记录一次请求指标(线程安全, 不抛异常不影响主流程)"""
    try:
        with METRICS_LOCK:
            METRICS["requests_total"] += 1
            key = (method, path.split("?")[0])
            METRICS["requests"][key] = METRICS["requests"].get(key, 0) + 1
            if isinstance(status, int):
                METRICS["status_codes"][status] = METRICS["status_codes"].get(status, 0) + 1
                if status >= 500:
                    METRICS["errors_total"] += 1
    except Exception:
        pass


def uptime():
    try:
        return max(0, int(time.time() - METRICS["uptime_start"]))
    except Exception:
        return 0
