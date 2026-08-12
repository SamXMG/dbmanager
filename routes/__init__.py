# -*- coding: utf-8 -*-
"""dbmanager - 路由按领域拆分(分发顺序: 连接→查询→结构→文件→存储过程→监控→管理)"""
from routes import admin, connection, files, monitor, query, routines, schema

ROUTE_MODS = [connection, query, schema, files, routines, monitor, admin]
