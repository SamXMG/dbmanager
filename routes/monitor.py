# -*- coding: utf-8 -*-
"""dbmanager - routes.monitor: 健康检查 + Prometheus 指标
- /api/health    : 探活端点(Docker/K8s liveness/readiness), 无需登录
- /api/metrics   : Prometheus 文本格式指标, 供 Prometheus/Grafana 采集, 无需登录
两个端点均不含业务数据, 已加入鉴权豁免(_auth_blocked/_must_change_blocked);
公网暴露时仍受网关令牌保护(_gateway_blocked 不豁免)。
"""
import os
import sys

from core import auth
from core import config
from infra.metrics import METRICS, METRICS_LOCK, uptime


def _send_text(handler, code, text, ctype="text/plain; version=0.0.4; charset=utf-8"):
    """发送纯文本响应(Prometheus 格式非 JSON)"""
    handler._last_status = code
    handler.send_response(code)
    handler.send_header("Content-Type", ctype)
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(text.encode("utf-8"))


def handle_get(handler, path, q):
    """GET 路由: 已处理返回 True, 否则 False"""
    if path == "/api/health":
        health = {
            "status": "ok",
            "version": config.VERSION,
            "uptime_seconds": uptime(),
            "pid": os.getpid(),
            "auth_required": auth.auth_enabled(),
            "sessions": len(auth.USER_SESSIONS),
            "requests_total": METRICS.get("requests_total", 0),
            "errors_total": METRICS.get("errors_total", 0),
            "python": sys.version.split()[0],
        }
        handler._send_json(200, health)
        return True
    if path == "/api/metrics":
        lines = []
        lines.append("# HELP dbm_uptime_seconds Process uptime in seconds")
        lines.append("# TYPE dbm_uptime_seconds gauge")
        lines.append("dbm_uptime_seconds %d" % uptime())
        lines.append("# HELP dbm_requests_total Total HTTP requests")
        lines.append("# TYPE dbm_requests_total counter")
        lines.append("dbm_requests_total %d" % METRICS.get("requests_total", 0))
        lines.append("# HELP dbm_errors_total HTTP 5xx responses")
        lines.append("# TYPE dbm_errors_total counter")
        lines.append("dbm_errors_total %d" % METRICS.get("errors_total", 0))
        lines.append("# HELP dbm_auth_sessions Active login sessions")
        lines.append("# TYPE dbm_auth_sessions gauge")
        lines.append("dbm_auth_sessions %d" % len(auth.USER_SESSIONS))
        lines.append("# HELP dbm_requests_by_path Requests by method and path")
        lines.append("# TYPE dbm_requests_by_path counter")
        with METRICS_LOCK:
            reqs = dict(METRICS.get("requests", {}))
            codes = dict(METRICS.get("status_codes", {}))
        for (m, p), cnt in sorted(reqs.items()):
            lines.append('dbm_requests_by_path{method="%s",path="%s"} %d'
                         % (m, p.replace("\\", "\\\\").replace('"', '\\"'), cnt))
        lines.append("# HELP dbm_status_codes Responses by HTTP status")
        lines.append("# TYPE dbm_status_codes counter")
        for st, cnt in sorted(codes.items()):
            lines.append('dbm_status_codes{code="%d"} %d' % (st, cnt))
        _send_text(handler, 200, "\n".join(lines) + "\n")
        return True
    return False


def handle_post(handler, path, q):
    """POST 路由(monitor 无写接口, 保持分发器兼容)"""
    return False
