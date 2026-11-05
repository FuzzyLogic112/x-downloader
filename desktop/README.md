# 桌面版

图形界面：粘贴推文链接 / 推文 ID / video.twimg.com 直链（一行一个，可批量），
选择画质，一键下载推文里的视频（多条全下）+ 元数据 JSON。

## 直接运行（已装 Python 3.8+）

```bash
python x_app.py
```

Windows 也可以双击 `启动下载器.bat`。

## 打包成 EXE（Windows）

双击 `打包成EXE.bat`：自动安装 PyInstaller（如未装），1–2 分钟后在 `dist/` 得到
`推特视频下载器.exe`——单文件免安装，拷到任何 Windows 电脑双击就能用，不用再装 Python。

也可以直接从本仓库的 [Releases](https://github.com/FuzzyLogic112/x-downloader/releases)
下载编好的 exe（每次推送都会自动构建并更新到 `latest`）。

## macOS / Linux

```bash
bash build-mac-linux.sh   # 生成 dist/x-downloader（同平台可执行文件）
```

## 说明

- 下载目录默认程序旁的 `downloads/`，可在界面里改；画质与目录选择会记住（`app_settings.json`）。
- 仅支持公开推文；受保护、已删除、需登录的推文会报错。
- 打包原理：PyInstaller `--onefile --windowed`，引擎 `x-dl.py` 通过 `--add-data` 一起打进 exe。
