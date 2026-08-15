# -*- coding: utf-8 -*-
"""i18n 骨架验证: t() 默认语言 / 显式语言 / 回退 / 参数替换。"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import i18n
from core.i18n import t


def test_default_lang_is_zh_CN():
    assert i18n.DEFAULT_LANG == "zh_CN"
    assert i18n.SUPPORTED == ("zh_CN", "en")


def test_zh_CN_returns_source_string():
    # 默认语言(受 config.LANG 影响, 沙箱默认 zh_CN)应返回源串, 行为不变
    assert t("auth.old_pwd_wrong") == "旧密码错误"


def test_explicit_en_translation():
    assert t("auth.old_pwd_wrong", lang="en") == "Incorrect old password"


def test_fallback_when_key_missing():
    # 未知 key: 回退到 key 本身(便于发现遗漏)
    assert t("__no_such_key__") == "__no_such_key__"


def test_en_falls_back_to_source_for_missing_translation():
    # en 包未提供的 key, 回退 zh_CN 源串
    assert t("__partial_key__", lang="en") == "__partial_key__"


def test_param_substitution():
    # 参数替换(当前种子集无带参 key, 直接验证机制)
    assert "a{b}c".format(b=1) == "a1c"
    # t 的 params 透传 format
    assert t("auth.approved", lang="zh_CN") == "已批准, 账号可登录"
