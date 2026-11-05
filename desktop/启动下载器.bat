@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 没找到 Python，请先去 python.org 安装 Python 3，安装时勾选 Add python.exe to PATH。
  pause
  exit /b 1
)
python x_app.py
pause
