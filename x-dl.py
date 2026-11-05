#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
x-dl.py -- 推特/X 视频下载器（独立解析版，零第三方依赖）
用法：
    python3 x-dl.py <推文链接 | 推文ID | video.twimg.com 直链> [选项]

选项：
    --quality best|1080|720|480|360|lowest   默认 best（取该推文里最高的清晰度）
    --out DIR                                下载目录（默认当前目录）
    --list                                   只列出可下载的清晰度，不下载
    --index N                                推文含多条视频时，指定下载第 N 条（从 1 起，默认全部）
    --no-meta                                不写元数据 .json

解析原理（独立，不依赖任何第三方下载站）：
    推文页 https://x.com/i/status/<id> 的服务端渲染 HTML 里本身就带有
    该推文全部视频的 video.twimg.com 直链（各清晰度 MP4 + m3u8），
    本工具只是用浏览器 UA 抓取该页面并用正则提取直链，不调用任何
    第三方解析后端、不需要 API Key、不需要登录。

注意：
    - 仅下载公开推文；受保护/需登录/已删除的推文会解析失败并如实报错。
    - 只下载你有权使用的视频；请遵守 X 的使用条款与原作者版权。
    - X 随时可能改页面结构，若解析失败请先确认推文公开且链接正确。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.0.0"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# video.twimg.com 直链：.../vid/avc1/<宽>x<高>/<token>.mp4（整条 URL 直接捕获）
VID_RE = re.compile(
    r"(https://video\.twimg\.com/(?:ext_tw_video|amplify_video)/"
    r"(\d+)/[^\"'\\ ]*?vid/avc1/(\d+)x(\d+)/[^\"'\\? ]+\.mp4"
    r"(?:\?[^\"'\\ ]*)?)")
# 备用：m3u8 播放列表（不直接下载，只作"有视频"的佐证）
M3U8_RE = re.compile(
    r"https://video\.twimg\.com/(?:ext_tw_video|amplify_video)/"
    r"(\d+)/[^\"'\\ ]*?\.m3u8(?:\?[^\"'\\ ]*)?")
TWEET_ID_RE = re.compile(r"(?:twitter\.com|x\.com)/(?:\w+/)?status/(\d+)")
BARE_ID_RE = re.compile(r"^\d{10,25}$")


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_input(s):
    """返回 ('tweet', id) 或 ('direct', url)。"""
    s = s.strip()
    if "video.twimg.com" in s and s.startswith("http"):
        return ("direct", s)
    m = TWEET_ID_RE.search(s)
    if m:
        return ("tweet", m.group(1))
    if BARE_ID_RE.match(s):
        return ("tweet", s)
    raise ValueError("无法识别的输入：请给推文链接、推文 ID 或 video.twimg.com 直链")


def fetch_tweet_videos(tweet_id):
    """抓取推文页，提取全部视频变体。返回 {media_id: [(w,h,url), ...]}。"""
    url = "https://x.com/i/status/%s" % tweet_id
    try:
        html = http_get(url).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        raise RuntimeError("推文页请求失败：HTTP %s（推文可能不存在/需登录/已删除）" % e.code)
    except Exception as e:
        raise RuntimeError("推文页请求失败：%s" % e)
    videos = {}
    for full, media_id, w, h in VID_RE.findall(html):
        w, h = int(w), int(h)
        videos.setdefault(media_id, [])
        if (w, h, full) not in videos[media_id]:
            videos[media_id].append((w, h, full))
    if not videos and M3U8_RE.search(html):
        raise RuntimeError("推文含视频但未提取到 MP4 直链（页面结构可能已变）")
    if not videos:
        if "doesn't exist" in html or "no longer exists" in html:
            raise RuntimeError("推文不存在或账号已不存在")
        raise RuntimeError("该推文未找到视频（可能为纯文字/图片推文，或需登录查看）")
    for mid in videos:
        videos[mid].sort(key=lambda t: (t[0] * t[1]), reverse=True)
    return videos


def pick_quality(variants, quality):
    """variants 已按清晰度降序。返回选中的 (w,h,url)。"""
    if quality == "best":
        return variants[0]
    if quality == "lowest":
        return variants[-1]
    try:
        want = int(quality)
    except ValueError:
        raise ValueError("--quality 只支持 best/1080/720/480/360/lowest")
    for v in variants:
        if v[1] == want:
            return v
    # 无精确匹配：取不高于目标的最高清晰度
    lower = [v for v in variants if v[1] <= want]
    if lower:
        return lower[0]
    return variants[-1]


def download(url, dest, retries=3):
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                with open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        if total:
                            print("\r  下载中 %d/%d MB (%.0f%%)" % (
                                got // 1048576, total // 1048576, got * 100.0 / total),
                                end="", flush=True)
                print()
                if total and got < total:
                    raise RuntimeError("下载不完整（%d/%d 字节）" % (got, total))
                return got
        except Exception as e:
            print("\n  第 %d 次下载失败：%s" % (attempt, e))
            if attempt == retries:
                raise
            time.sleep(2)
    raise RuntimeError("下载失败")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="推特/X 视频下载器 v%s（独立解析，零依赖）" % VERSION)
    ap.add_argument("input", help="推文链接 / 推文 ID / video.twimg.com 直链")
    ap.add_argument("--quality", default="best",
                    help="best|1080|720|480|360|lowest（默认 best）")
    ap.add_argument("--out", default=".", help="下载目录（默认当前目录）")
    ap.add_argument("--list", action="store_true", help="只列出清晰度，不下载")
    ap.add_argument("--index", type=int, default=0,
                    help="推文含多条视频时指定第 N 条（从 1 起；默认全部下载）")
    ap.add_argument("--no-meta", action="store_true", help="不写元数据 .json")
    args = ap.parse_args(argv)

    try:
        kind, value = parse_input(args.input)
    except ValueError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 2

    os.makedirs(args.out, exist_ok=True)

    if kind == "direct":
        print("直链模式：直接下载")
        print("  %s" % value)
        dest = os.path.join(args.out, os.path.basename(value.split("?")[0]))
        try:
            size = download(value, dest)
        except Exception as e:
            print("错误：%s" % e, file=sys.stderr)
            return 1
        print("已保存：%s（%.1f MB）" % (dest, size / 1048576.0))
        return 0

    tweet_id = value
    print("解析推文：https://x.com/i/status/%s" % tweet_id)
    try:
        videos = fetch_tweet_videos(tweet_id)
    except RuntimeError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 1

    print("找到 %d 条视频：" % len(videos))
    for i, (mid, variants) in enumerate(videos.items(), 1):
        print("  [%d] 媒体 %s：%s" % (
            i, mid, "、".join("%dx%d" % (w, h) for w, h, _ in variants)))

    if args.list:
        return 0

    all_videos = list(videos.items())
    if args.index:
        if args.index < 1 or args.index > len(all_videos):
            print("错误：--index 超出范围（共 %d 条视频）" % len(all_videos), file=sys.stderr)
            return 2
        targets = [(args.index, all_videos[args.index - 1])]
    else:
        targets = list(enumerate(all_videos, 1))

    saved = []
    for i, (mid, variants) in targets:
        w, h, url = pick_quality(variants, args.quality)
        fname = "x_%s_%d_%dx%d.mp4" % (tweet_id, i, w, h)
        dest = os.path.join(args.out, fname)
        print("下载 [%d] %dx%d：" % (i, w, h))
        print("  %s" % url)
        try:
            size = download(url, dest)
        except Exception as e:
            print("错误：%s" % e, file=sys.stderr)
            return 1
        print("已保存：%s（%.1f MB）" % (dest, size / 1048576.0))
        saved.append({"index": i, "media_id": mid, "width": w, "height": h,
                      "url": url, "file": fname, "bytes": size})

    if not args.no_meta:
        meta = {"tweet_id": tweet_id,
                "tweet_url": "https://x.com/i/status/%s" % tweet_id,
                "quality_requested": args.quality,
                "videos": saved}
        mpath = os.path.join(args.out, "x_%s.json" % tweet_id)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print("元数据：%s" % mpath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
