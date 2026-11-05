#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推特/X 视频下载器 · Web 版（零依赖，Python 3 标准库）

给 Hark 这类「没有 MCP、只能开浏览器操作」的 AI 用的入口：
Hark 打开这个页面，粘贴推文链接，点解析、点下载即可。

启动：
  python3 server.py                 # 默认 0.0.0.0:8902
  PORT=9000 python3 server.py       # 自定义端口
  X_DL_CODE=你的口令 python3 server.py   # 建议：公网部署时开启访问口令

接口：
  GET  /                        网页界面
  POST /api/parse  {url}        解析推文链接 → 各视频及清晰度列表
  GET  /api/download?tweet_id=&index=&q=   代理下载指定视频（q=best/1080/720/480/360/lowest）

解析原理与 CLI 版相同：抓推文页 SSR HTML，提取 video.twimg.com 直链。
仅用于公开推文，请尊重原作者版权。
"""
import importlib.util
import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "x-dl.py")
PORT = int(os.environ.get("PORT", "8902"))
ACCESS_CODE = os.environ.get("X_DL_CODE", "").strip()

_spec = importlib.util.spec_from_file_location("x_dl_engine", ENGINE)
eng = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eng)

CACHE = {}  # tweet_id -> {"videos": {...}, "ts": float}
import time
CACHE_TTL = 1800

PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>推特视频下载器</title>
<style>
body{font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#111}
h1{font-size:22px} input{width:100%;padding:12px;font-size:15px;box-sizing:border-box;border:1px solid #ccc;border-radius:8px}
button{margin-top:12px;padding:11px 22px;font-size:15px;border:0;border-radius:8px;background:#1d9bf0;color:#fff;cursor:pointer}
button:disabled{opacity:.5}
#out{margin-top:20px;font-size:14px;line-height:1.7}
.vid{border:1px solid #e5e5e5;border-radius:10px;padding:12px;margin-top:12px}
.vid a{display:inline-block;margin:4px 8px 4px 0;padding:6px 12px;border-radius:6px;background:#e8f5fe;color:#1d9bf0;text-decoration:none}
.err{color:#c00}
.mut{color:#666;font-size:13px}
</style></head><body>
<h1>推特 / X 视频下载器</h1>
<p class="mut">粘贴推文链接，解析后选择清晰度下载。支持 x.com / twitter.com 的推文链接、推文 ID、video.twimg.com 直链。</p>
<input id="u" placeholder="https://x.com/xxx/status/1234567890..." autocomplete="off">
<br><button id="go" onclick="go()">解析</button>
<div id="out"></div>
<script>
async function go(){
  const u=document.getElementById('u').value.trim();
  const out=document.getElementById('out');
  if(!u){out.innerHTML='<p class="err">请先粘贴推文链接</p>';return;}
  document.getElementById('go').disabled=true;
  out.innerHTML='<p>解析中…</p>';
  try{
    const r=await fetch('/api/parse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});
    const d=await r.json();
    if(d.error){out.innerHTML='<p class="err">'+d.error+'</p>';return;}
    let h='<p>推文 '+d.tweet_id+'：共 '+d.videos.length+' 条视频</p>';
    d.videos.forEach(v=>{
      h+='<div class="vid"><b>视频 '+v.index+'</b>（'+v.variants.map(x=>x.w+'x'+x.h).join(' / ')+'）<br>';
      v.variants.forEach(x=>{
        h+='<a href="/api/download?tweet_id='+d.tweet_id+'&index='+v.index+'&q='+x.h+'" download>下载 '+x.h+'p</a>';
      });
      h+='</div>';
    });
    out.innerHTML=h;
  }catch(e){out.innerHTML='<p class="err">请求失败：'+e+'</p>';}
  document.getElementById('go').disabled=false;
}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _check_code(self):
        if not ACCESS_CODE:
            return True
        # 口令可放在请求头 X-Access-Code，或 ?code= 参数
        if self.headers.get("X-Access-Code") == ACCESS_CODE:
            return True
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        return q.get("code", [""])[0] == ACCESS_CODE

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/download":
            if not self._check_code():
                return self._send(403, json.dumps({"error": "需要访问口令"}))
            q = parse_qs(u.query)
            tid = q.get("tweet_id", [""])[0]
            idx = int(q.get("index", ["1"])[0])
            want = q.get("q", ["best"])[0]
            entry = CACHE.get(tid)
            if not entry or time.time() - entry["ts"] > CACHE_TTL:
                try:
                    videos = eng.fetch_tweet_videos(tid)
                except Exception as e:
                    return self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False))
                CACHE[tid] = {"videos": videos, "ts": time.time()}
                entry = CACHE[tid]
            items = list(entry["videos"].items())
            if idx < 1 or idx > len(items):
                return self._send(400, json.dumps({"error": "视频序号超出范围"}))
            mid, variants = items[idx - 1]
            try:
                w, h, url = eng.pick_quality(variants, want)
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False))
            # 代理下载：从 video.twimg.com 拉流，转给浏览器
            try:
                req = urllib.request.Request(url, headers={"User-Agent": eng.UA})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    total = resp.headers.get("Content-Length")
                    fname = "x_%s_%d_%dx%d.mp4" % (tid, idx, w, h)
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Disposition",
                                     'attachment; filename="%s"' % fname)
                    if total:
                        self.send_header("Content-Length", total)
                    self.end_headers()
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except Exception as e:
                # 头已发出则无法再返回 JSON；仅记录
                sys.stderr.write("download proxy error: %s\n" % e)
            return
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        from urllib.parse import urlparse
        u = urlparse(self.path)
        if u.path != "/api/parse":
            return self._send(404, json.dumps({"error": "not found"}))
        if not self._check_code():
            return self._send(403, json.dumps({"error": "需要访问口令"}))
        try:
            body = json.loads(self.rfile.read(
                int(self.headers.get("Content-Length") or 0) or 0).decode("utf-8"))
        except Exception:
            return self._send(400, json.dumps({"error": "请求体不是合法 JSON"}))
        url = (body.get("url") or "").strip()
        try:
            kind, value = eng.parse_input(url)
        except ValueError as e:
            return self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False))
        if kind == "direct":
            return self._send(200, json.dumps({
                "tweet_id": None, "direct": True, "url": value,
                "note": "直链模式：浏览器直接打开该地址即可下载"}, ensure_ascii=False))
        try:
            videos = eng.fetch_tweet_videos(value)
        except RuntimeError as e:
            return self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False))
        CACHE[value] = {"videos": videos, "ts": time.time()}
        out = {"tweet_id": value, "videos": []}
        for i, (mid, variants) in enumerate(videos.items(), 1):
            out["videos"].append({
                "index": i, "media_id": mid,
                "variants": [{"w": w, "h": h, "url": u} for w, h, u in variants]})
        self._send(200, json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("x-dl web 已启动：http://0.0.0.0:%d  （口令：%s）"
          % (PORT, "已设置" if ACCESS_CODE else "未设置"))
    srv.serve_forever()
