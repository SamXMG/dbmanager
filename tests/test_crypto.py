# -*- coding: utf-8 -*-
"""core.crypto 安全单测(P1-2): 固化存储加密(AES-GCM)与传输加密(RSA-OAEP)行为。

隔离策略: 测试前将 config.BASE_DIR 指向临时目录, 使机器密钥(.dbm_key)与
RSA 私钥(.dbm_rsa)生成在临时区, 不污染真实工作目录; 结束后清理。
用法: python tests/test_crypto.py
"""
import os
import sys
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix="dbm_crypto_")
os.environ["DBM_DB_FILE"] = os.path.join(_TMP, "dbmanager.db")

# 必须在 import crypto 之前把 BASE_DIR 指向临时目录(隔离密钥文件)
from core import config  # noqa: E402
config.BASE_DIR = _TMP

import core.crypto as crypto  # noqa: E402


def check(name, cond, extra=""):
    if cond:
        print("  ✓", name)
    else:
        print("  ✗", name, extra)
    assert cond, "%s %s" % (name, extra)


def teardown():
    shutil.rmtree(_TMP, ignore_errors=True)


# ---------- 1) 存储加密 AES-GCM 往返 ----------
def test_pwd_encrypt_roundtrip():
    for plain in ["", "short", "中文密码/!@#", "a" * 2000]:
        blob = crypto.encrypt_pwd(plain)
        if plain == "":
            check("空密码返回空字符串", blob == "")
            continue
        dec = crypto.decrypt_pwd(blob)
        check("AES-GCM 往返一致: %r" % plain[:20], dec == plain,
              "解密=%r" % dec)


# ---------- 2) 密文篡改应解密失败(GCM 完整性保护) ----------
def test_pwd_tamper_detected():
    blob = crypto.encrypt_pwd("secret-password")
    raw = bytearray(__import__("base64").b64decode(blob))
    raw[-1] ^= 0x01  # 翻转末位密文比特
    tampered = __import__("base64").b64encode(bytes(raw)).decode("ascii")
    try:
        crypto.decrypt_pwd(tampered)
        check("篡改密文被 GCM 拒绝", False, "未抛异常")
    except Exception:
        check("篡改密文被 GCM 拒绝", True)


# ---------- 3) 传输层 RSA-OAEP 往返 ----------
def test_rsa_roundtrip():
    pem = crypto.rsa_public_pem()
    check("RSA 公钥为 PEM 格式", pem.startswith("-----BEGIN PUBLIC KEY-----"))
    plain = "user-login-password-中文"
    # 用 PyCryptodome 公钥加密(RSA-OAEP/SHA-256, 与前端 WebCrypto 一致)
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_OAEP
    from Crypto.Hash import SHA256
    import base64
    pub = RSA.import_key(pem)
    cipher = PKCS1_OAEP.new(pub, hashAlgo=SHA256)
    enc = base64.b64encode(cipher.encrypt(plain.encode("utf-8"))).decode("ascii")
    dec = crypto.rsa_decrypt(enc)
    check("RSA-OAEP 往返一致", dec == plain, "解密=%r" % dec)


# ---------- 4) maybe_decrypt_pwd 分支 ----------
def test_maybe_decrypt_pwd():
    raw = "plain-password"
    check("无前缀原样返回", crypto.maybe_decrypt_pwd(raw) == raw)
    # rsa: 前缀走解密
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_OAEP
    from Crypto.Hash import SHA256
    import base64
    pub = RSA.import_key(crypto.rsa_public_pem())
    enc = base64.b64encode(
        PKCS1_OAEP.new(pub, hashAlgo=SHA256).encrypt(raw.encode("utf-8"))
    ).decode("ascii")
    check("rsa: 前缀解密", crypto.maybe_decrypt_pwd("rsa:" + enc) == raw)


if __name__ == "__main__":
    try:
        test_pwd_encrypt_roundtrip()
        test_pwd_tamper_detected()
        test_rsa_roundtrip()
        test_maybe_decrypt_pwd()
        print()
        print("core.crypto 单测全部通过 ✓")
    finally:
        teardown()
