#!/bin/bash
# macOS / Linux 下打包（生成同平台可执行文件，不是 Windows exe）
cd "$(dirname "$0")"
python3 -m pip install pyinstaller -q
python3 -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name "x-downloader" --add-data "../x-dl.py:." x_app.py
echo "完成：dist/x-downloader"
