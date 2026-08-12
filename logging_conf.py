# -*- coding: utf-8 -*-
"""结构化日志: 控制台 + logs/dbmanager.log(5MB × 3 轮转)
用法: app.py 入口调用 setup_logging() 一次; 各模块 import logging 后
     logger = logging.getLogger(__name__) 使用, 不再直接 print。
"""
import logging
import os
from logging.handlers import RotatingFileHandler

_BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(_BASE, "logs")
LOG_FILE = os.path.join(LOG_DIR, "dbmanager.log")
FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """初始化根 logger: 控制台 + 文件轮转。幂等(已配置则跳过)。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:  # 避免重复 handler(多线程/重入)
        return
    fmt = logging.Formatter(FMT, datefmt="%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024,
                             backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)
