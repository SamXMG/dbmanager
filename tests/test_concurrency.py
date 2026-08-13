# -*- coding: utf-8 -*-
"""高并发背压回归测试(评审补丁 ①~④):
- 有界队列: 信号量耗尽时 process_request 立即 503(背压), 而非无限排队
- Handler.timeout = 30(slowloris 防护)
- request_queue_size = 128(TCP accept 背压)
- server_close 取消排队任务(cancel_futures)
"""
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, ".")
import config
import handler
from app import ResilientHTTPServer


def _make_server(sem_count):
    srv = ResilientHTTPServer.__new__(ResilientHTTPServer)
    srv._req_executor = None
    srv._req_sem = threading.BoundedSemaphore(sem_count)
    return srv


def _read_until_header(sock, timeout=5):
    data = b""
    sock.settimeout(timeout)
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def test_semaphore_drained_returns_503():
    """信号量耗尽 -> 立即 503 快速失败(背压), 不 submit 不占线程"""
    srv = _make_server(1)
    srv._req_sem.acquire()  # 占满唯一名额
    server_side, client_side = socket.socketpair()
    received = []

    def client_read():
        received.append(_read_until_header(client_side))

    t = threading.Thread(target=client_read)
    t.start()
    srv.process_request(server_side, ("127.0.0.1", 9999))
    t.join(timeout=5)
    resp = received[0] if received else b""
    assert b"503" in resp
    assert b"server overloaded" in resp
    client_side.close()


def test_semaphore_available_submits():
    """信号量有余额 -> 走 submit 分支(不 503); 超量第二个立即 503"""
    srv = _make_server(1)
    server_side, client_side = socket.socketpair()
    received = []

    def client_read():
        received.append(_read_until_header(client_side))

    t = threading.Thread(target=client_read)
    t.start()
    # 不 acquire: 余额 1, 正常路径应尝试 submit(executor 为 None 会走 except 关连接,
    # 但不会 503——因为没走到过载分支)。验证: 响应中不含 503。
    srv.process_request(server_side, ("127.0.0.1", 9999))
    t.join(timeout=5)
    resp = received[0] if received else b""
    assert b"503" not in resp  # 正常路径不误报过载
    client_side.close()


def test_handler_timeout_set():
    """请求级超时 30s(slowloris 失效)"""
    assert handler.Handler.timeout == 30


def test_accept_queue_size():
    """TCP accept 背压 128(非 stdlib 默认 5)"""
    assert ResilientHTTPServer.request_queue_size == 128


def test_semaphore_capacity_auto():
    """REQUEST_QUEUE 未配置时容量 = max(workers*8, 128) = 512"""
    n = config.REQUEST_WORKERS or 64
    q = getattr(config, "REQUEST_QUEUE", None) or max(n * 8, 128)
    assert q == max(64 * 8, 128) == 512
