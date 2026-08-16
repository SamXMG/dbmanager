# -*- coding: utf-8 -*-
"""统一错误脱敏: 供 server.handler 与各 routes 共用, 避免脱敏逻辑漂移。

业务校验错误(ValueError)与数据库错误(SQLAlchemyError, 含语法错误/
表不存在等, 对用户排查 SQL 有直接价值)以及开发模式(DBM_DEV=1)透传详情;
其余内部异常(代码 bug 等)对外只给通用消息, 防止泄露内部细节。
"""

import logging

from core.config import conf

logger = logging.getLogger("dbmanager")


def safe_error(e):
    """返回对外安全的错误消息字符串(内部异常详情打到结构化日志)。"""
    if isinstance(e, ValueError) or conf("DBM_DEV"):
        return str(e)
    try:
        from sqlalchemy.exc import SQLAlchemyError
        if isinstance(e, SQLAlchemyError):
            return str(e)
    except Exception:
        pass
    # 脱敏前把原始异常打到结构化日志(控制台 + logs/dbmanager.log), 便于排查
    logger.error("内部错误(已脱敏): %s: %s", type(e).__name__, e, exc_info=True)
    return "服务器内部错误（设置 DBM_DEV=1 可查看详细错误）"
