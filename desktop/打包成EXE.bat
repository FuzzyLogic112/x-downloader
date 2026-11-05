@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 推特视频下载器 - 打包成 EXE
echo ============================================
echo   推特视频下载器：一键打包成独立 EXE
echo   （只需这一次，之后双击 EXE 就能用）
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
  echo [×] 没找到 Python。请先去 python.org 下载安装 Python 3，
  echo     安装时务必勾选 "Add python.exe to PATH"，再回来双击本文件。
  pause
  exit /b 1
)
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
  echo 正在安装打包工具 PyInstaller（只装一次）…
  python -m pip install pyinstaller
)
set ICON=
if exist icon.ico set ICON=--icon icon.ico
echo 正在打包，请稍候（1-2 分钟）…
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "推特视频下载器" %ICON% --add-data "..\x-dl.py;." x_app.py
if errorlevel 1 (
  echo [×] 打包失败，看上面的报错信息。
  pause
  exit /b 1
)
echo.
echo [√] 打包完成！程序在 dist 文件夹里：dist\推特视频下载器.exe
echo     把它拷到任何地方（桌面/U盘/其他电脑）双击就能用，不用再装 Python。
pause
