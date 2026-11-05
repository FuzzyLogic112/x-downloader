@echo off
chcp 65001 >nul
title 推特视频下载器
cd /d %~dp0
where python >nul 2>nul
if %errorlevel% neq 0 (
  echo 没找到 Python，请先去 python.org 安装 Python 3，安装时勾选 Add python.exe to PATH。
  pause
  exit /b
)
python x-dl.py
pause
