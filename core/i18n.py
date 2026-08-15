# -*- coding: utf-8 -*-
"""轻量 i18n(无第三方依赖): 字典式查找 + 参数替换 + 回退。

用法:
    from core.i18n import t
    t("auth.old_pwd_wrong")                 # 默认语言(由 config.LANG 决定, 默认 zh_CN)
    t("auth.old_pwd_wrong", lang="en")      # 显式指定
    t("common.deleted_n", n=3)              # 带参数替换 {n}

语言由 config.LANG 控制: 环境变量 DBM_LANG 或 dbmanager.conf [i18n] lang, 默认 zh_CN。

迁移约定(增量): 任何用户可见文案, 新增 key 到 locales/zh_CN.json(源) 与
locales/en.json(译文), 代码用 t("key") 取代硬编码串。zh_CN 值应与原串一致,
保证默认语言下行为字节级不变。
"""

import json
import os
from typing import Any, Dict, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_DIR = os.path.join(BASE_DIR, "locales")
SUPPORTED = ("zh_CN", "en")
DEFAULT_LANG = "zh_CN"
FALLBACK = "zh_CN"


def _load(lang: str) -> Dict[str, str]:
    path = os.path.join(LOCALE_DIR, "%s.json" % lang)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# 进程内一次性加载(语言包不会热更); 缺失文件回退为空字典。
_CATALOGS = {lang: _load(lang) for lang in SUPPORTED}


def current_lang() -> str:
    """返回当前生效语言(来自 config.LANG, 非法值回退默认)。"""
    from core.config import LANG  # 惰性导入, 避免与 config 的潜在循环(实际无环)

    return LANG if LANG in SUPPORTED else DEFAULT_LANG


def t(key: str, lang: Optional[str] = None, **params: Any) -> str:
    """翻译 key; 缺失 key 回退到 FALLBACK, 再缺失则返回 key 本身(便于发现遗漏)。"""
    lang = lang or current_lang()
    if lang not in _CATALOGS:
        lang = FALLBACK
    cat = _CATALOGS.get(lang) or {}
    text = cat.get(key)
    if text is None:
        text = (_CATALOGS.get(FALLBACK) or {}).get(key, key)
    if params:
        try:
            text = text.format(**params)
        except Exception:
            pass
    return text
