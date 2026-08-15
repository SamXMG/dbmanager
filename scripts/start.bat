@echo off
REM DB Manager one-click launcher (Windows double-click)
REM All logic lives in manage.py; this is only a thin shell.
cd /d "%~dp0.."
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"
%PY% manage.py start --fg
if errorlevel 1 pause
