@echo off
chcp 65001 >nul
title dbmanager 一键部署/启动
setlocal
echo ============================================
echo   dbmanager 部署与启动脚本
echo ============================================
echo.

REM ---- 选择 Python: 优先项目虚拟环境(WorkBuddy 自带, 依赖已装), 其次 PATH python ----
set "VENV_PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
set "PY="

if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import Crypto, sqlalchemy" >nul 2>&1
  if not errorlevel 1 (
    set "PY=%VENV_PY%"
    echo [1/3] 使用项目虚拟环境(依赖已就绪)
  ) else (
    echo [1/3] 虚拟环境存在但缺依赖, 正在安装...
    "%VENV_PY%" -m pip install --upgrade pip >nul 2>&1
    "%VENV_PY%" -m pip install -r "%~dp0..\requirements.txt"
    if errorlevel 1 (
      echo [重试] 默认源失败, 切换清华镜像源...
      "%VENV_PY%" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r "%~dp0..\requirements.txt"
      if errorlevel 1 (
        echo [错误] 依赖安装失败(默认源与清华源均失败), 请检查网络后重试
        pause
        exit /b 1
      )
    )
    set "PY=%VENV_PY%"
    echo     依赖安装完成
  )
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [错误] 未找到 python。请先安装 Python 3.10+:
    echo    https://www.python.org/downloads/
    echo   安装时务必勾选 "Add python.exe to PATH"
    pause
    exit /b 1
  )
  echo [1/3] 使用系统 Python, 安装依赖...
  python -m pip install --upgrade pip >nul 2>&1
  python -m pip install -r "%~dp0..\requirements.txt"
  if errorlevel 1 (
    echo [重试] 默认源失败, 切换清华镜像源...
    python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r "%~dp0..\requirements.txt"
    if errorlevel 1 (
      echo [错误] 依赖安装失败(默认源与清华源均失败),请检查网络后重试
      pause
      exit /b 1
    )
  )
  set "PY=python"
  echo     依赖安装完成
)
echo.

echo [2/3] 检测 SQL Server ODBC 驱动...
"%PY%" -c "import pyodbc; ds = pyodbc.drivers(); print('     可用驱动:', ds if ds else '(无)')" 2>nul
"%PY%" -c "import pyodbc; ds = pyodbc.drivers(); ok = [d for d in ds if 'SQL Server' in d or 'SQLServer' in d]; exit(0 if ok else 1)" >nul 2>&1
if errorlevel 1 (
  echo [提示] 未找到 SQL Server ODBC 驱动。
  echo   如需连接 SQL Server,请安装:
  echo   https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server
  echo   注意位数: 64 位 Python 需 64 位驱动
  echo.
) else (
  echo     驱动正常
  echo.
)

echo [3/3] 启动工具...
echo.
echo 提示: 首次启动会自动打开浏览器 http://127.0.0.1:8770
echo 关闭本窗口即停止工具。
echo 若要后台运行, 请改在命令行执行: "%PY%" app.py
echo ============================================
cd /d "%~dp0.."
"%PY%" app.py
pause
