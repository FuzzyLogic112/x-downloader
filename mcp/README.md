# MCP 版

零依赖 stdio MCP 服务器 `x_mcp_server.py`，复用根目录的 `x-dl.py` 引擎，
让支持 MCP 的 AI 客户端（Claude Code / Codex / Cursor / Windsurf 等）把推特视频下载当成本地工具直接调用。

## 工具

| 工具 | 作用 |
|---|---|
| `x_parse` | 只解析不下载：返回推文里各视频及清晰度直链（1920x1080 / 1280x720 / 640x360 / 480x270 等） |
| `x_download` | 按指定清晰度下载视频 + 元数据 JSON，返回绝对路径和文件大小 |

## 接入

### Claude Code

```bash
claude mcp add x-downloader -e X_DOWNLOAD_DIR="D:\x-downloads" -- python3 "D:\x-downloader\mcp\x_mcp_server.py"
claude mcp list    # 验证
```

或直接改 MCP 配置文件（`~/.claude.json` 或项目 `.mcp.json`），格式见 `mcp.json.example`。

### Codex

```bash
codex mcp add x-downloader -- python3 "D:\x-downloader\mcp\x_mcp_server.py"
codex mcp list     # 验证
```

或写 `~/.codex/config.toml`：

```toml
[mcp_servers.x-downloader]
command = "python3"
args = ["D:\\x-downloader\\x_mcp_server.py"]
env = { X_DOWNLOAD_DIR = "D:\\x-downloads" }
```

### 其他 MCP 客户端

按 `mcp.json.example` 的格式填：`command` 为 `python3`，`args` 为 `x_mcp_server.py` 的绝对路径，
可选环境变量 `X_DOWNLOAD_DIR` 指定下载目录（默认引擎目录下的 `downloads/`），
`X_DL_PATH` 可指定 `x-dl.py` 的位置（默认先找服务器同目录、再找父目录）。

## 使用

接入后直接对 AI 说：

> 下载这条推文的视频：https://x.com/xxx/status/1234567890

AI 会先调 `x_parse` 看有几条视频、哪些清晰度，再调 `x_download` 下载。
只想先看不下载时说"先解析一下这条推文"。

## 说明

- 仅支持公开推文；受保护、已删除、需登录的推文会返回明确的错误。
- 引擎的进度输出会被重定向，不会污染 MCP 的 stdio 通道。
- Python 3.8+，零第三方依赖。
