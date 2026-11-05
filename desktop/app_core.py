# -*- coding: utf-8 -*-
"""
APP 逻辑层（无界面）：把引擎 x-dl.py 的流程接到回调上，供图形界面调用，也可独立测试。
- LogTap：接管 print 输出，行回调给日志区；"下载中 NN%"行转成进度回调。
- run_downloads：批量下载（推文链接 / 推文 ID / video.twimg.com 直链，一行一个）。
注意：靠重定向 sys.stdout 工作，同一时刻只跑一个任务（界面会禁用按钮）。
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import sys

def _find_engine():
    cands = []
    env = os.environ.get("X_DL_PATH", "").strip()
    if env:
        cands.append(env)
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.join(here, "x-dl.py"))
    cands.append(os.path.join(os.path.dirname(here), "x-dl.py"))
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        cands.append(os.path.join(meipass, "x-dl.py"))
    cands.append(os.path.join(os.getcwd(), "x-dl.py"))
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None

ENGINE_PATH = _find_engine()
_engine = None

def load_engine():
    global _engine
    if _engine is not None:
        return _engine
    if not ENGINE_PATH:
        raise RuntimeError("找不到 x-dl.py：请把它放在程序同目录或上级目录，或设置 X_DL_PATH。")
    spec = importlib.util.spec_from_file_location("x_dl_engine", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _engine = mod
    return mod

class LogTap(io.TextIOBase):
    def __init__(self, on_line, on_progress):
        self.on_line = on_line
        self.on_progress = on_progress
        self._buf = ""
        # 引擎的进度行是 "下载中 5/8 MB (64%)" 这种形式：取括号里的百分比
        self._prog_re = re.compile(r"下载中.*?(\d+)%")

    def write(self, s):
        if not s:
            return 0
        self._buf += s
        while True:
            m = re.search(r"[\r\n]", self._buf)
            if not m:
                break
            seg, self._buf = self._buf[:m.start()], self._buf[m.end():]
            self._emit(seg)
        return len(s)

    def _emit(self, seg):
        seg = seg.strip()
        if not seg:
            return
        pm = self._prog_re.search(seg)
        if pm:
            try:
                self.on_progress(int(pm.group(1)))
            except Exception:
                pass
            return
        self.on_line(seg)

    def flush(self):
        if self._buf.strip():
            self._emit(self._buf)
            self._buf = ""

def _items_from_blob(blob):
    return [ln.strip() for ln in (blob or "").splitlines() if ln.strip()]

def run_downloads(blob, out_dir, quality, on_line, on_progress, on_status):
    eng = load_engine()
    items = _items_from_blob(blob)
    if not items:
        on_line("没有可下载的链接。")
        return
    os.makedirs(out_dir, exist_ok=True)
    total = len(items)
    done = 0
    for raw in items:
        on_status("正在处理 %d/%d…" % (done + 1, total))
        try:
            kind, value = eng.parse_input(raw)
        except ValueError as e:
            on_line("✗ 无法识别：%s（%s）" % (raw, e))
            done += 1
            continue
        tap = LogTap(on_line, lambda p, d=done, t=total: on_progress(int((d + p / 100.0) / t * 100)))
        try:
            with contextlib.redirect_stdout(tap):
                if kind == "direct":
                    fname = os.path.basename(value.split("?")[0])
                    dest = os.path.join(out_dir, fname)
                    size = eng.download(value, dest)
                    tap.flush()
                    on_line("✓ 已保存：%s（%.1f MB）" % (dest, size / 1048576.0))
                else:
                    videos = eng.fetch_tweet_videos(value)
                    on_line("解析推文 %s：找到 %d 条视频" % (value, len(videos)))
                    for i, (mid, variants) in enumerate(videos.items(), 1):
                        on_line("  [%d] %s" % (i, "、".join("%dx%d" % (w, h) for w, h, _ in variants)))
                        w, h, url = eng.pick_quality(variants, quality)
                        fname = "x_%s_%d_%dx%d.mp4" % (value, i, w, h)
                        dest = os.path.join(out_dir, fname)
                        on_line("下载 [%d] %dx%d…" % (i, w, h))
                        size = eng.download(url, dest)
                        tap.flush()
                        on_line("✓ 已保存：%s（%.1f MB）" % (dest, size / 1048576.0))
                    meta = {"tweet_id": value,
                            "tweet_url": "https://x.com/i/status/%s" % value,
                            "quality_requested": quality}
                    with open(os.path.join(out_dir, "x_%s.json" % value), "w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            tap.flush()
            on_line("✗ 失败：%s" % e)
        done += 1
        on_progress(int(done / total * 100))
    on_status("完成：%d/%d 条处理完毕，文件在 %s" % (done, total, out_dir))
