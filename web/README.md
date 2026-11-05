# 推特视频下载器 · Web 版（给 Hark 用）

## 为什么是网页版，不是 MCP

Hark（2026-10 上线）**目前不支持 MCP**，没有插件、没有 API，官方也没有开发者接入文档。
它干活的方式是：在云端开浏览器、登录网站、像人一样点来点去。
所以本地 Python 脚本、stdio MCP 它都接不上——唯一能用的入口是**一个它能打开的网页**。

这个 Web 版就是干这个的：零依赖（Python 3 标准库），一个页面，粘贴推文链接 → 解析 → 点清晰度下载。

## 本地试用

```bash
python3 server.py            # http://127.0.0.1:8902
PORT=9000 python3 server.py  # 换端口
```

## 给 Hark 用：部署到公网（以你的 VPS 为例）

Hark 的浏览器在云端，打不开你电脑上的 localhost，必须部署到公网地址。

```bash
# 1. 把 x-web 文件夹和 x-dl.py 传到 VPS
# 2. 在 VPS 上启动（带访问口令，防止别人白嫖）：
X_DL_CODE=你定的口令 PORT=8902 nohup python3 server.py &
# 3. 放行防火墙 8902 端口，拿到地址：http://你的VPS-IP:8902
```

然后给 Hark 的任务这样写：

> 打开 http://你的VPS-IP:8902/?code=你定的口令，在输入框粘贴这条推文链接：<推文链接>，
> 点"解析"，下载最高清的那条视频，把下载好的文件发给我。

## 接口（给其他 AI / 脚本调用）

- `GET /` 网页界面
- `POST /api/parse` `{"url": "推文链接"}` → 推文 ID、各视频及清晰度列表
- `GET /api/download?tweet_id=…&index=1&q=best` → 代理下载（q=best/1080/720/480/360/lowest）
- 访问口令：请求头 `X-Access-Code: 口令` 或 URL 参数 `?code=口令`

## 本地实测（2026-11-05）

- `/api/parse` 解析 Leviwoyun 推文成功，3 条视频各 4 档清晰度
- `/api/download` 代理下载成功，488x360 MP4，ffprobe 校验通过
