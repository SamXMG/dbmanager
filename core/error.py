# -*- coding: utf-8 -*-
"""统一错误脱敏: 供 server.handler 与各 routes 共用, 避免脱敏逻辑漂移。

仅两类异常对外透传原始消息:
  1) ValueError —— 业务校验错误(如端口非法), 不含内部细节;
  2) 开发模式(DBM_DEV=1) —— 排错用, 全部透传。
其余(含 SQLAlchemyError: 表名/列名/约束名/SQL 片段等内部结构)一律脱敏,
原始详情仅写入结构化日志, 防止数据库结构泄露给前端用户。
"""

import logging

from core.config import conf

logger = logging.getLogger("dbmanager")


def _should_expose(e):
    """判定异常原始消息是否可对外透传。

    SQLAlchemyError 不在此列: 其 str() 常含表名/列名/约束名(如
    'relation "users" does not exist' / 'column "x" of relation "y"'),
    即便语法错误也可能回显原 SQL, 直接透传即泄露库结构。
    """
    if isinstance(e, ValueError):
        return True
    if conf("DBM_DEV"):
        return True
    return False


def safe_error(e):
    """返回对外安全的错误消息字符串(内部异常详情打到结构化日志)。"""
    if _should_expose(e):
        return str(e)
    # 脱敏前把原始异常打到结构化日志(控制台 + logs/dbmanager.log), 便于排查
    logger.error("内部错误(已脱敏): %s: %s", type(e).__name__, e, exc_info=True)
    return "服务器内部错误（设置 DBM_DEV=1 可查看详细错误）"
