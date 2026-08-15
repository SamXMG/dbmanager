@echo off
rem 局域网访问启动脚本
rem 推荐方式: 编辑 dbmanager.conf 将 [server] host 改为 0.0.0.0, 然后直接 python app.py 或本脚本
rem 本脚本另设 DBM_HOST=0.0.0.0 作为显式覆盖(环境变量优先级最高), 兼容不改配置文件的一键启动
rem 其他电脑通过 http://本机IP:8770 访问; 本机 IP 用 ipconfig 查看
rem 提示: 首次使用需以管理员运行一次防火墙放行(见 README 局域网访问说明)
cd /d "%~dp0.."
set DBM_HOST=0.0.0.0
python app.py
pause
