# -*- coding: utf-8 -*-
""" 刷新并获取本机全局(公网) IPv6，输出 DB Manager 的公网访问地址。
前置：路由器已开启 IPv6（前缀下发 / SLAAC 或 DHCPv6-PD）。
用法：python get_ipv6.py   （建议以管理员运行，renew6 需要提权；SLAAC 自动获取则无需）
"""
import subprocess
import re
import ipaddress
import sys

ADAPTER = "WLAN"  # 活动网卡名（中文 Windows 通常为 WLAN）


def _run(cmd, timeout=25):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except Exception as e:
        return None


def renew():
    # 触发 IPv6 地址续租；SLAAC 下 RA 会自动到达，此步可选
    r = _run(["ipconfig", "/renew6", ADAPTER])
    if r is not None and r.returncode != 0:
        err = r.stderr.decode("gbk", "ignore").strip() or r.stdout.decode("gbk", "ignore").strip()
        if err:
            print("  (renew6 提示: %s —— 若已自动获取可忽略)" % err)


def get_global_v6():
    out = _run(["ipconfig"])
    if not out:
        return {}
    txt = out.stdout.decode("gbk", "ignore")
    found = {}
    for ln in txt.splitlines():
        low = ln.lower()
        if "ipv6" not in low or ":" not in ln:
            continue
        val = ln.rsplit(":", 1)[1].strip()
        val = re.split(r"[\s(]", val, maxsplit=1)[0].strip()
        if "%" in val:
            val = val.split("%")[0]
        if not val:
            continue
        try:
            ip = ipaddress.ip_address(val)
        except Exception:
            continue
        s = str(ip).lower()
        if s.startswith(("fe80", "fc", "fd")) or ip.is_loopback:
            continue
        is_temp = ("临时" in ln) or ("temporary" in low)
        if s not in found:
            found[s] = is_temp
    return found


if __name__ == "__main__":
    print("正在刷新 IPv6 地址 (%s) ..." % ADAPTER)
    renew()
    found = get_global_v6()
    if not found:
        print("\n仍未发现全局 IPv6。请确认：")
        print("  1) 路由器已开启 IPv6（前缀下发 / SLAAC 或 DHCPv6-PD），并保存生效")
        print("  2) 等待 10~30 秒让 RA 下发，或在网络适配器里「禁用/启用」WLAN")
        print("  3) 若仍无，请以管理员身份重跑本脚本（renew6 需提权）")
        sys.exit(0)
    print("\n发现全局 IPv6 地址：")
    for ip, is_temp in found.items():
        tag = "临时/temporary(出方向,可能变化)" if is_temp else "稳定/stable(用于入站访问)"
        print("  [%s] %s" % (tag, ip))
        if not is_temp:
            print("  -> 公网访问地址： https://[%s]:8770" % ip)
            print("     浏览器会提示自签名证书「不安全」，点「高级 -> 继续访问」即可；")
            print("     进入后输入网关令牌 (.dbm_gateway) 完成验证。")
