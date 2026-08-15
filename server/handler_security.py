# -*- coding: utf-8 -*-
"""dbmanager - handler_security: 网关令牌 / HTTPS·SSL / 内网判定(优化路线图 1.1 handler 拆分)。
从 handler.py 独立; 由 handler.py re-export 保持旧引用兼容。
"""
import datetime
import hashlib
import ipaddress
import logging
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time

from core import config
from core.config import conf

logger = logging.getLogger("handler_security")


# ------------------------------
# 公网访问网关验证（仅对“外部/公网”客户端生效；内网/回环免验证）
# - 网关令牌优先级：环境变量 DBM_GATEWAY_TOKEN > 已保存的 .dbm_gateway > 启动时随机生成（落地 .dbm_gateway，权限 600）
# - 外部客户端必须携带网关令牌（Cookie: dbm_gw 或请求头 X-Gateway-Token）方可访问任何 API
# - 内网（RFC1918 / 回环 / 链路本地 / IPv6 ULA）客户端无需额外验证，保持局域网免密
# ------------------------------
GATEWAY_TOKEN_FILE = os.path.join(config.BASE_DIR, ".dbm_gateway")


def _load_gateway_token():
    env = conf("DBM_GATEWAY_TOKEN")
    if env:
        return env
    tf = GATEWAY_TOKEN_FILE
    if os.path.exists(tf):
        try:
            t = open(tf, "r", encoding="utf-8").read().strip()
            if t:
                return t
        except Exception:
            pass
    t = secrets.token_urlsafe(24)
    try:
        with open(tf, "w", encoding="utf-8") as _f:
            _f.write(t)
        try:
            os.chmod(tf, 0o600)
        except Exception:
            pass
        logger.warning("=" * 64)
        logger.warning("⚠ 已自动生成公网访问网关令牌（请妥善保存，重启后不变；")
        logger.warning("  也可设置环境变量 DBM_GATEWAY_TOKEN 固定令牌）：")
        logger.warning("   " + t)
        logger.warning("=" * 64)
    except Exception:
        pass
    sys.stdout.flush()
    return t


GATEWAY_TOKEN = _load_gateway_token()
GATEWAY_HASH = hashlib.sha256(GATEWAY_TOKEN.encode("utf-8")).hexdigest()

# 网关会话(登录成功签发随机 token, cookie 只存会话 id, 不存哈希本身, 可单独吊销)
GATEWAY_SESSIONS: dict[str, float] = {}       # token -> 过期时间戳
GATEWAY_SESSION_TTL = 8 * 3600
# 登录限流: 按客户端 IP 计数, 连续失败超阈值锁定, 防暴力破解
GATEWAY_FAIL: dict[str, list] = {}           # IP -> [连续失败次数, 首次失败时间戳]
GATEWAY_MAX_FAIL = 5        # 连续失败 5 次
GATEWAY_LOCK_SEC = 300      # 锁定 5 分钟

# ------------------------------
# HTTPS / SSL（公网强烈建议开启；自签名证书可自动生成，亦支持自带证书）
# - 显式证书：设置环境变量 DBM_SSL_CERT / DBM_SSL_KEY
# - 一键自签名：设置 DBM_SSL=1 即自动生成自签名证书(.dbm_cert.pem/.dbm_key_ssl.pem)并启用
# - 启用后 ipaddress 判定、Cookie 的 Secure 标记、api_base 的 https 协议均自动联动
# ------------------------------
SSL_CERT = None
SSL_KEY = None
USE_HTTPS = False


def _gen_self_signed_cert(cert_path, key_path):
    """生成自签名证书（覆盖 localhost / 127.0.0.1 / ::1 / 本机可达 IP），有效期 825 天。"""
    sans = ["DNS:localhost", "IP:127.0.0.1", "IP:::1"]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ip.startswith("127.") or ip == "::1":
                continue
            sans.append("IP:" + ip)
    except Exception:
        pass
    san = ",".join(sorted(set(sans)))
    openssl = shutil.which("openssl") or "openssl"
    cmd = [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
           "-keyout", key_path, "-out", cert_path, "-days", "825",
           "-subj", "/CN=DBManager.local", "-addext", "subjectAltName=" + san]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        # openssl 不可用时回退 cryptography（需 pip install cryptography）
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            sub = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DBManager.local")])
            sans_list = [x509.DNSName("localhost"),
                         x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                         x509.IPAddress(ipaddress.ip_address("::1"))]
            cert = (x509.CertificateBuilder().subject_name(sub).issuer_name(sub)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
                    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=825))
                    .add_extension(x509.SubjectAlternativeName(sans_list), critical=False)
                    .sign(key, hashes.SHA256()))
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(serialization.Encoding.PEM,
                                          serialization.NoEncryption()))
        except Exception:
            raise RuntimeError("生成自签名证书失败：openssl 不可用且未安装 cryptography")
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass


def _ssl_setup():
    """解析 SSL 证书来源并设置全局 USE_HTTPS / SSL_CERT / SSL_KEY。"""
    global SSL_CERT, SSL_KEY, USE_HTTPS
    cert = conf("DBM_SSL_CERT")
    key = conf("DBM_SSL_KEY")
    if cert and key:
        SSL_CERT, SSL_KEY, USE_HTTPS = cert, key, True
        return
    dcert = os.path.join(config.BASE_DIR, ".dbm_cert.pem")
    dkey = os.path.join(config.BASE_DIR, ".dbm_key_ssl.pem")
    # DBM_SSL=1(或 dbmanager.conf [server] ssl=1) 或已存在默认自签名证书时启用
    if conf("DBM_SSL") == "1" or os.path.exists(dcert):
        if not (os.path.exists(dcert) and os.path.exists(dkey)):
            try:
                _gen_self_signed_cert(dcert, dkey)
            except Exception as e:
                logger.error("自签名证书生成失败：%s", e)
                sys.stdout.flush()
                return
        SSL_CERT, SSL_KEY, USE_HTTPS = dcert, dkey, True


def _is_https():
    return USE_HTTPS


def _scheme():
    return "https" if _is_https() else "http"


def _client_is_internal(handler):
    """根据客户端源地址判断是否为内网/回环（免网关验证）。"""
    raw = handler.client_address[0]
    try:
        ip = ipaddress.ip_address(raw)
    except Exception:
        return False
    if ip.version == 6 and getattr(ip, "ipv4_mapped", None) is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _gateway_cookie_ok(handler):
    cookie = handler.headers.get("Cookie", "")
    now = time.time()
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("dbm_gw="):
            val = part[len("dbm_gw="):]
            if val and val in GATEWAY_SESSIONS:
                if GATEWAY_SESSIONS[val] > now:
                    return True
                GATEWAY_SESSIONS.pop(val, None)  # 过期会话顺带清理
    if len(GATEWAY_SESSIONS) > 5000:  # 防字典无限增长
        for k, exp in list(GATEWAY_SESSIONS.items()):
            if exp <= now:
                GATEWAY_SESSIONS.pop(k, None)
    tok = handler.headers.get("X-Gateway-Token")
    if tok and hashlib.sha256(tok.encode("utf-8")).hexdigest() == GATEWAY_HASH:
        return True
    return False


def _gateway_allowed(handler):
    if _client_is_internal(handler):
        return True
    return _gateway_cookie_ok(handler)
