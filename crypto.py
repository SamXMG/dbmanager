# -*- coding: utf-8 -*-
"""dbmanager - 加密存储
连接密码: AES-GCM 加密落盘(密钥存 .dbm_key), 传输层 RSA-OAEP 解密, Windows 下可用 DPAPI。
依赖: pycryptodome (Crypto)。
"""
import base64
import ctypes
import os
import secrets
import sys

import config

# ------------------------------
# 连接加密存储（密码 AES-GCM 加密落盘，密钥存本机文件，权限 600）
# 行为对齐 Navicat：配置文件里只存密文，明文密码不出现在磁盘上。
# 密钥与机器绑定（存于 .dbm_key），换机器则无法解密，需重新输入密码。
# ------------------------------
try:
    from Crypto.Cipher import AES, PKCS1_OAEP
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import RSA as _RSA
except ImportError:
    # 启动引导信息: 此时 logging 可能未初始化, basicConfig 兜底(幂等)
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(message)s")
    logging.error("=" * 64)
    logging.error("缺少依赖 pycryptodome（提供 Crypto 模块），无法加密存储密码。")
    logging.error("请先安装依赖，二选一：")
    logging.error("  1) 双击 setup_new_pc.bat（自动安装并启动）")
    logging.error("  2) 命令行执行: python -m pip install -r requirements.txt")
    logging.error("=" * 64)
    raise SystemExit(1)

def _key_file():
    return os.path.join(config.BASE_DIR, ".dbm_key")

def _conn_file():
    return os.path.join(config.BASE_DIR, "connections.json")

def _load_key():
    kf = _key_file()
    if os.path.exists(kf):
        try:
            with open(kf, "rb") as _f:
                return base64.b64decode(_f.read().strip())
        except Exception:
            pass
    key = secrets.token_bytes(32)
    with open(kf, "wb") as _f:
        _f.write(base64.b64encode(key))
    try:
        os.chmod(kf, 0o600)
    except Exception:
        pass
    return key

def _use_dpapi():
    """Windows 上用 DPAPI(密钥绑定当前用户账户), 其他平台回退 AES-GCM"""
    return sys.platform.startswith("win")

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong),
                ("pbData", ctypes.POINTER(ctypes.c_byte))]

def _dpapi_protect(data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

def _dpapi_unprotect(data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

def encrypt_pwd(plain):
    """存储加密: Windows 用 DPAPI(密钥绑定用户账户, 拷走目录也解不开);
    其他平台回退 AES-GCM(机器密钥文件 .dbm_key)。输出 v2: 前缀标记 DPAPI。"""
    if not plain:
        return ""
    if _use_dpapi():
        try:
            return "v2:" + base64.b64encode(_dpapi_protect(plain.encode("utf-8"))).decode("ascii")
        except Exception:
            pass  # 回退 AES
    key = _load_key()
    iv = secrets.token_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    ct, tag = cipher.encrypt_and_digest(plain.encode("utf-8"))
    return base64.b64encode(iv + tag + ct).decode("ascii")

def decrypt_pwd(blob):
    """解密存储密码; 兼容旧版 AES-GCM 密文(无 v2: 前缀)"""
    if not blob:
        return ""
    if blob.startswith("v2:") and _use_dpapi():
        try:
            return _dpapi_unprotect(base64.b64decode(blob[3:])).decode("utf-8")
        except Exception:
            pass  # 跨平台迁移等场景回退 AES 尝试
    key = _load_key()
    data = base64.b64decode(blob)
    iv, tag, ct = data[:12], data[12:28], data[28:]
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    return cipher.decrypt_and_verify(ct, tag).decode("utf-8")

# ------------------------------
# 传输层密码加密(RSA 公钥加密, 防 HTTP 抓包)
# 前端用 /api/pubkey 下发的公钥加密密码, 密文带 "rsa:" 前缀; 服务端私钥解密
# ------------------------------
def _load_rsa_key():
    kf = os.path.join(config.BASE_DIR, ".dbm_rsa")
    if os.path.exists(kf):
        try:
            return _RSA.import_key(open(kf, "rb").read())
        except Exception:
            pass
    key = _RSA.generate(2048)
    try:
        with open(kf, "wb") as _f:
            _f.write(key.export_key("PEM"))
        try:
            os.chmod(kf, 0o600)   # 复核 P0-R3: 私钥仅本用户可读(Linux/Mac 同机防提权读)
        except Exception:
            pass
    except Exception:
        pass
    return key

def rsa_public_pem() -> str:
    """下发公钥(PEM)给前端用于加密密码"""
    return _load_rsa_key().publickey().export_key("PEM").decode("ascii")

def rsa_decrypt(cipher_b64: str) -> str:
    # 前端 WebCrypto 使用 RSA-OAEP/SHA-256, 这里必须一致, 否则解密失败
    return PKCS1_OAEP.new(_load_rsa_key(), hashAlgo=SHA256).decrypt(base64.b64decode(cipher_b64)).decode("utf-8")

def maybe_decrypt_pwd(pwd):
    """传输层解密: 'rsa:' 前缀表示前端用公钥加密的密码, 解密为明文; 否则原样返回"""
    if isinstance(pwd, str) and pwd.startswith("rsa:"):
        return rsa_decrypt(pwd[4:])
    return pwd
