@echo off
REM 一键获取本机公网 IPv6 并打印 DB Manager 访问地址
REM 建议：右键「以管理员身份运行」（renew6 需要提权；SLAAC 自动获取则无需）
"C:\Users\10294\.workbuddy\binaries\python\envs\default\Scripts\python.exe" "%~dp0..\infra\ipv6.py"
pause
