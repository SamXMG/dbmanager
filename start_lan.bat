@echo off
rem 局域网访问启动脚本: 监听所有网卡(0.0.0.0)
rem 其他电脑通过 http://本机IP:8770 访问; 本机 IP 用 ipconfig 查看
rem 提示: 首次使用需以管理员运行一次防火墙放行(见 README 局域网访问说明)
set DBM_HOST=0.0.0.0
python app.py
pause
