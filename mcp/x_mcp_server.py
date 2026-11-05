#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X / Twitter Downloader MCP Server (zero-dependency, stdio transport)

Wraps the existing x-dl.py engine as MCP tools so any MCP-compatible
AI client (Claude Code / Codex / Cursor / Windsurf / Muse, etc.)
can call it as a native tool instead of guessing CLI arguments.

Tools:
  x_parse     Parse a tweet link / tweet ID / video.twimg.com link -> all videos
              and their quality variants (MP4 direct links). No download.
  x_download  Download the video(s) of a tweet at a chosen quality, plus
              metadata JSON. Returns absolute file paths and sizes.

Protocol: MCP over stdio, newline-delimited JSON-RPC 2.0.
No third-party packages: Python 3.8+ standard library only.

Engine lookup order for x-dl.py:
  1. $X_DL_PATH (full path to x-dl.py)
  2. Same directory as this server file
  3. Parent directory of this server file
  4. Current working directory

Default download directory: $X_DOWNLOAD_DIR, else ./downloads beside the engine.

NOTE: the engine prints progress to stdout, which would corrupt the MCP
stdio channel, so every engine call is wrapped in redirect_stdout.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import traceback

SERVER_NAME = "x-downloader"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2024-11-05"


# ---------------- engine loading ----------------

def find_engine_path():
    candidates = []
    env = os.environ.get("X_DL_PATH", "").strip()
    if env:
        candidates.append(env)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "x-dl.py"))
    candidates.append(os.path.join(os.path.dirname(here), "x-dl.py"))
    candidates.append(os.path.join(os.getcwd(), "x-dl.py"))
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


ENGINE_PATH = find_engine_path()
_engine = None


def load_engine():
    global _engine
    if _engine is not None:
        return _engine
    if not ENGINE_PATH:
        raise RuntimeError(
            "x-dl.py not found. Put it beside this server, in the parent "
            "directory, or set X_DL_PATH to its full path.")
    spec = importlib.util.spec_from_file_location("x_dl_engine", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _engine = mod
    return mod


def default_out_dir():
    env = os.environ.get("X_DOWNLOAD_DIR", "").strip()
    if env:
        return env
    base = os.path.dirname(ENGINE_PATH) if ENGINE_PATH else os.getcwd()
    return os.path.join(base, "downloads")


def snapshot(d):
    out = {}
    if os.path.isdir(d):
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                try:
                    out[name] = os.path.getsize(p)
                except OSError:
                    pass
    return out


# ---------------- tool implementations ----------------

def tool_parse(args):
    eng = load_engine()
    raw = (args.get("url") or "").strip()
    if not raw:
        raise ValueError("missing required argument: url")
    try:
        kind, value = eng.parse_input(raw)
    except ValueError as e:
        return {"success": False, "error": "bad_input", "message": str(e)}
    if kind == "direct":
        return {"success": True, "direct": True, "url": value,
                "message": "Direct video.twimg.com link: download it as-is; "
                           "its resolution is fixed and cannot be raised."}
    try:
        videos = eng.fetch_tweet_videos(value)
    except RuntimeError as e:
        return {"success": False, "error": "parse_failed", "tweet_id": value,
                "message": str(e)}
    out_videos = []
    for i, (mid, variants) in enumerate(videos.items(), 1):
        out_videos.append({
            "index": i, "media_id": mid,
            "variants": [{"width": w, "height": h, "url": u}
                         for w, h, u in variants]})
    return {"success": True, "tweet_id": value,
            "tweet_url": "https://x.com/i/status/%s" % value,
            "video_count": len(out_videos), "videos": out_videos}


def tool_download(args):
    eng = load_engine()
    raw = (args.get("url") or "").strip()
    if not raw:
        raise ValueError("missing required argument: url")
    quality = args.get("quality") or "best"
    if quality not in ("best", "1080", "720", "480", "360", "lowest"):
        raise ValueError("quality must be one of: best, 1080, 720, 480, 360, lowest")
    index = args.get("index") or 0
    out_dir = (args.get("output_dir") or "").strip() or default_out_dir()
    os.makedirs(out_dir, exist_ok=True)
    try:
        kind, value = eng.parse_input(raw)
    except ValueError as e:
        return {"success": False, "error": "bad_input", "message": str(e)}
    before = snapshot(out_dir)
    buf = io.StringIO()
    saved = []
    try:
        with contextlib.redirect_stdout(buf):
            if kind == "direct":
                fname = os.path.basename(value.split("?")[0])
                dest = os.path.join(out_dir, fname)
                size = eng.download(value, dest)
                saved.append({"index": 1, "file": fname,
                              "path": dest, "size_bytes": size, "url": value})
                tweet_id = None
            else:
                videos = eng.fetch_tweet_videos(value)
                items = list(videos.items())
                if index:
                    if index < 1 or index > len(items):
                        return {"success": False, "error": "index_out_of_range",
                                "message": "Tweet has %d video(s); index %d is out of range."
                                           % (len(items), index)}
                    targets = [(index, items[index - 1])]
                else:
                    targets = list(enumerate(items, 1))
                for i, (mid, variants) in targets:
                    w, h, url = eng.pick_quality(variants, quality)
                    fname = "x_%s_%d_%dx%d.mp4" % (value, i, w, h)
                    dest = os.path.join(out_dir, fname)
                    size = eng.download(url, dest)
                    saved.append({"index": i, "media_id": mid,
                                  "width": w, "height": h, "url": url,
                                  "file": fname, "path": dest,
                                  "size_bytes": size})
                tweet_id = value
    except RuntimeError as e:
        return {"success": False, "error": "download_failed",
                "message": str(e), "engine_log_tail": buf.getvalue().strip()[-800:]}
    except Exception as e:
        return {"success": False, "error": "tool_exception",
                "message": "%s: %s" % (type(e).__name__, e),
                "engine_log_tail": buf.getvalue().strip()[-800:]}
    after = snapshot(out_dir)
    files = []
    for s in saved:
        if os.path.isfile(s["path"]):
            files.append(s)
    meta = None
    if tweet_id:
        meta = {"tweet_id": tweet_id,
                "tweet_url": "https://x.com/i/status/%s" % tweet_id,
                "quality_requested": quality, "videos": saved}
        mpath = os.path.join(out_dir, "x_%s.json" % tweet_id)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        files.append({"file": os.path.basename(mpath), "path": mpath,
                      "size_bytes": os.path.getsize(mpath)})
    return {"success": True, "output_dir": out_dir, "quality": quality,
            "files": files, "metadata": meta,
            "engine_log_tail": buf.getvalue().strip()[-800:]}


TOOLS = [
    {
        "name": "x_parse",
        "description": ("Parse a tweet (X / Twitter) link, tweet ID, or video.twimg.com direct link "
                        "and return all videos in the tweet with their quality variants (MP4 direct links, "
                        "e.g. 1920x1080 / 1280x720 / 640x360 / 480x270). Does NOT download anything. "
                        "Use this first to inspect a tweet before downloading. "
                        "Only public tweets work; protected, deleted or login-only tweets fail with a clear error."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string",
                        "description": "Tweet link (e.g. https://x.com/user/status/1234567890), tweet ID, or a video.twimg.com direct link."}
            },
            "required": ["url"],
        },
    },
    {
        "name": "x_download",
        "description": ("Download the video(s) of a tweet (X / Twitter) at the chosen quality and return the "
                        "absolute file paths, sizes and a metadata JSON. Downloads every video in the tweet "
                        "by default; use index to download only one. Long videos take a while; the call blocks "
                        "until the download finishes. Direct video.twimg.com links download as-is (fixed resolution)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string",
                        "description": "Tweet link, tweet ID, or video.twimg.com direct link."},
                "quality": {"type": "string", "enum": ["best", "1080", "720", "480", "360", "lowest"],
                            "default": "best",
                            "description": "best = highest available variant; a number picks that height if available, otherwise the highest not above it."},
                "index": {"type": "integer",
                          "description": "If the tweet has several videos, download only the Nth one (1-based). Omit to download all."},
                "output_dir": {"type": "string",
                               "description": "Optional output directory. Default: $X_DOWNLOAD_DIR or <engine dir>/downloads."},
            },
            "required": ["url"],
        },
    },
]

TOOL_FUNCS = {"x_parse": tool_parse, "x_download": tool_download}


# ---------------- MCP / JSON-RPC plumbing ----------------

def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def log(msg):
    sys.stderr.write("[x-mcp] %s\n" % msg)
    sys.stderr.flush()


def handle(req):
    method = req.get("method", "")
    rid = req.get("id")
    params = req.get("params") or {}
    is_notification = rid is None

    def result(payload):
        if not is_notification:
            send({"jsonrpc": "2.0", "id": rid, "result": payload})

    def error(code, message):
        if not is_notification:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})

    try:
        if method == "initialize":
            client_proto = params.get("protocolVersion") or DEFAULT_PROTOCOL
            result({
                "protocolVersion": client_proto,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            })
        elif method in ("notifications/initialized", "notifications/cancelled"):
            pass
        elif method == "ping":
            result({})
        elif method == "tools/list":
            result({"tools": TOOLS})
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            fn = TOOL_FUNCS.get(name)
            if fn is None:
                result({"content": [{"type": "text", "text": "Unknown tool: %s" % name}],
                        "isError": True})
                return
            try:
                payload = fn(args)
                is_err = not payload.get("success", True)
                result({
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                    "structuredContent": payload,
                    "isError": is_err,
                })
            except Exception as e:
                log(traceback.format_exc())
                payload = {"success": False, "error": "tool_exception",
                           "message": "%s: %s" % (type(e).__name__, e)}
                result({
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                    "structuredContent": payload,
                    "isError": True,
                })
        else:
            error(-32601, "Method not found: %s" % method)
    except Exception as e:
        log(traceback.format_exc())
        error(-32603, "Internal error: %s: %s" % (type(e).__name__, e))


def main():
    log("starting v%s; engine: %s" % (SERVER_VERSION, ENGINE_PATH or "NOT FOUND"))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(req, list):
            for r in req:
                handle(r)
        else:
            handle(req)


if __name__ == "__main__":
    main()
