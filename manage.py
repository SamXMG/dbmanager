#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DB Manager 跨平台部署 / 进程管理脚本 (Windows / Linux / macOS)

一份逻辑, 全平台通用. 自动识别操作系统, 无需维护 .bat / .sh 两套.

用法:
  python manage.py start            # 部署并后台启动 (装依赖 + 构建前端 + 启动 app.py)
  python manage.py start --fg       # 前台启动 (调试用, 关终端即停)
  双击 manage.py (无参数)            # = start --fg, 面向 Windows 小白, 窗口保持可见
  python manage.py stop             # 停止并释放端口 (只杀 app.py 进程)
  python manage.py restart          # 重启
  python manage.py status           # 查看运行状态
  python manage.py build            # 仅构建前端

环境变量:
  DBM_PORT       监听端口 (默认 8770)
  DBM_FORCE_FE   1 = 强制重建前端 (否则 dist 存在则跳过)
  DBM_NO_KILL    1 = stop 时跳过杀进程 (仅清理 pid 文件)
"""
import argparse
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WIN = sys.platform.startswith("win")
PORT = os.environ.get("DBM_PORT") or "8770"
PIDFILE = ROOT / "dbmanager.pid"
LOGFILE = ROOT / "logs" / "dbmanager.log"

APP_MARK = "app.py"  # 仅匹配命令行含 app.py 的进程, 不误杀其他程序


def log(msg: str) -> None:
    print(f"[manage] {msg}")


def pick_python() -> str:
    """优先使用项目虚拟环境, 否则回退到当前解释器."""
    for name in (".venv", "venv", "env"):
        bin_dir = "Scripts" if IS_WIN else "bin"
        exe = "python.exe" if IS_WIN else "python"
        p = ROOT / name / bin_dir / exe
        if p.exists():
            log(f"使用虚拟环境 Python: {p}")
            return str(p)
    return sys.executable


def install_backend(py: str) -> None:
    req = ROOT / "requirements.lock"
    if not req.exists():
        req = ROOT / "requirements.txt"
    if not req.exists():
        log("未找到 requirements.lock / requirements.txt, 跳过依赖安装")
        return
    log(f"安装后端依赖: {req.name}")
    rc = subprocess.run([py, "-m", "pip", "install", "-r", str(req)],
                        cwd=str(ROOT)).returncode
    if rc != 0:
        log("依赖安装返回非零退出码 (pip 可能需联网重试), 继续...")


def build_frontend(force: bool = False) -> None:
    dist = ROOT / "frontend" / "dist" / "index.html"
    if not force and dist.exists():
        log("前端已构建, 跳过 (设 DBM_FORCE_FE=1 可强制重建)")
        return
    if not (ROOT / "frontend" / "package.json").exists():
        log("未找到 frontend/package.json, 跳过前端构建")
        return
    if not _find_exec("npm"):
        log("未检测到 npm, 跳过前端构建 (程序仍可用, 但无 Web 界面)")
        return
    cwd = str(ROOT / "frontend")
    log("构建前端 (Vue3)...")
    ci = subprocess.run(_npm_call("npm ci"), shell=IS_WIN, cwd=cwd)
    if ci.returncode != 0:
        log("npm ci 失败, 重试 npm install")
        subprocess.run(_npm_call("npm install"), shell=IS_WIN, cwd=cwd)
    subprocess.run(_npm_call("npm run build"), shell=IS_WIN, cwd=cwd)


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


def _find_exec(name: str) -> str | None:
    """检测可执行文件. Windows 上 npm 必须是 npm.cmd (CreateProcess 不能直接跑 .cmd)."""
    if IS_WIN and not name.lower().endswith(".cmd"):
        c = _which(name + ".cmd")
        if c:
            return c
    return _which(name)


def _npm_call(cmd: str):
    """返回给 subprocess 的调用形式: Windows 用 shell 串, POSIX 用列表."""
    return cmd if IS_WIN else cmd.split()


def _read_text(args, timeout: int = 30) -> str:
    """安全读取命令输出: 容忍命令不存在 / 非 UTF-8 (如 wmic 的 GBK)."""
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout)
        if not r.stdout:
            return ""
        return r.stdout.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def list_app_processes():
    """列出所有命令行含 APP_MARK 的 python 进程 -> [(pid, cmdline)]"""
    procs = []
    try:
        if IS_WIN:
            out = _read_text(
                ["wmic", "process", "get", "ProcessId,CommandLine", "/format:csv"])
            if out:
                for line in out.splitlines():
                    parts = line.split(",")
                    if len(parts) < 3:
                        continue
                    cmd = parts[1]
                    pid = parts[-1].strip()
                    if not (APP_MARK in cmd and pid.isdigit()):
                        continue
                    if "debugpy" in cmd.lower():  # 跳过 VS Code 调试器进程
                        continue
                    procs.append((int(pid), cmd.strip()))
                if procs:
                    return procs
            # fallback: powershell (wmic 在部分环境被移除/拦截)
            ps = ('Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -like \'*'
                  + APP_MARK + '*\' -and $_.CommandLine -notlike \'*debugpy*\'} | '
                  'ForEach-Object {"$($_.ProcessId)|$($_.CommandLine)"}')
            out = _read_text(["powershell", "-NoProfile", "-Command", ps])
            for line in out.splitlines():
                if "|" not in line:
                    continue
                pid_s, _, cmd = line.partition("|")
                if pid_s.isdigit():
                    procs.append((int(pid_s), cmd.strip()))
        else:
            out = _read_text(["ps", "-eo", "pid,args"])
            for line in out.splitlines()[1:]:
                line = line.strip()
                if not line:
                    continue
                pid_s, _, cmd = line.partition(" ")
                if APP_MARK in cmd and pid_s.isdigit():
                    procs.append((int(pid_s), cmd.strip()))
    except Exception as e:  # noqa: BLE001
        log(f"列举进程失败: {e}")
    return procs


def stop() -> None:
    if os.environ.get("DBM_NO_KILL") == "1":
        log("DBM_NO_KILL=1, 跳过杀进程")
    else:
        procs = list_app_processes()
        if not procs:
            log("未发现运行中的 dbmanager (app.py) 进程")
        for pid, cmd in procs:
            try:
                if IS_WIN:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True)
                else:
                    os.kill(pid, signal.SIGKILL)
                log(f"已停止 PID {pid}: {cmd[:60]}")
            except Exception as e:  # noqa: BLE001
                log(f"停止 PID {pid} 失败: {e}")
    if PIDFILE.exists():
        PIDFILE.unlink()
        log("已清理 pid 文件")


def start(foreground: bool = False) -> None:
    py = pick_python()
    install_backend(py)
    build_frontend(force=os.environ.get("DBM_FORCE_FE") == "1")

    app = ROOT / "app.py"
    if not app.exists():
        log(f"未找到 {app}, 无法启动")
        sys.exit(1)

    env = os.environ.copy()
    if foreground:
        log(f"前台启动 (关此终端即停): http://127.0.0.1:{PORT}")
        subprocess.run([py, str(app)], env=env, cwd=str(ROOT))
        return

    LOGFILE.parent.mkdir(parents=True, exist_ok=True)
    flags = 0
    kwargs = {}
    if IS_WIN:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | \
                getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    with open(LOGFILE, "a", encoding="utf-8") as lf:
        p = subprocess.Popen(
            [py, str(app)], env=env, cwd=str(ROOT),
            stdout=lf, stderr=subprocess.STDOUT,
            creationflags=flags, **kwargs,
        )
    PIDFILE.write_text(str(p.pid))
    time.sleep(1.0)
    alive = p.poll() is None
    if alive:
        log(f"已在后台启动 (PID {p.pid}), 日志: {LOGFILE}")
        log(f"访问: http://127.0.0.1:{PORT}  (局域网用本机 IP)")
        log("停止: python manage.py stop")
    else:
        log(f"启动失败 (进程已退出), 请查看日志: {LOGFILE}")


def status() -> None:
    procs = list_app_processes()
    if procs:
        log("运行中的进程:")
        for pid, cmd in procs:
            print(f"  PID {pid}: {cmd}")
    else:
        log("未运行")
    if PIDFILE.exists():
        pid_txt = PIDFILE.read_text().strip()
        log(f"pid 文件记录: {pid_txt} (若进程已不在, 可 python manage.py stop 清理)")


def main() -> None:
    # 双击启动 (无参数): 前台运行, 窗口保持可见, 关窗口即停 —— 面向 Windows 小白
    if len(sys.argv) == 1:
        log("双击启动模式: 前台运行 dbmanager (关此窗口即停止)")
        start(foreground=True)
        try:
            input("dbmanager 已停止. 按回车关闭窗口...")
        except EOFError:
            pass
        return

    parser = argparse.ArgumentParser(description="DB Manager 跨平台部署/进程管理")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "build"])
    parser.add_argument("--fg", action="store_true", help="前台启动 (仅 start 有效)")
    args = parser.parse_args()

    if args.action == "start":
        start(foreground=args.fg)
    elif args.action == "stop":
        stop()
    elif args.action == "restart":
        stop()
        time.sleep(0.5)
        start(foreground=args.fg)
    elif args.action == "status":
        status()
    elif args.action == "build":
        build_frontend(force=os.environ.get("DBM_FORCE_FE") == "1")


if __name__ == "__main__":
    main()
