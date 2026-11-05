# -*- coding: utf-8 -*-
"""
推特视频下载器 APP（图形界面）
- 粘贴推文链接 / 推文 ID / video.twimg.com 直链（一行一个，可批量），
  下载推文里的视频（多条全下，每条可选清晰度，最高 1080p）+ 元数据 JSON
打包：双击「打包成EXE.bat」用 PyInstaller 生成独立 exe（见 README）。
"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import app_core

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(APP_DIR, "app_settings.json")

QUALITY_LABELS = {
    "最高清（best）": "best",
    "1080p": "1080",
    "720p": "720",
    "480p": "480",
    "360p": "360",
    "最低清（lowest）": "lowest",
}


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(s):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def open_folder(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("推特视频下载器")
        self.geometry("780x620")
        self.minsize(680, 520)
        self.settings = load_settings()
        self.q = queue.Queue()
        self.busy = False
        self._build_ui()
        self.after(100, self._poll)
        # 测试钩子：X_APP_AUTODEMO=1 时自动填入示例链接并开始下载（用于截图验收）
        if os.environ.get("X_APP_AUTODEMO") == "1":
            demo = os.environ.get("X_APP_AUTODEMO_URL", "https://x.com/Leviwoyun/status/2118157743840469222/video/1")
            self.txt_links.insert("1.0", demo)
            self.after(600, self._start_download)

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}
        ttk.Label(self, text="粘贴推文链接 / 推文 ID / video.twimg.com 直链（一行一个，可多行批量）：").pack(anchor="w", **pad)
        self.txt_links = scrolledtext.ScrolledText(self, height=6, font=("Microsoft YaHei", 10))
        self.txt_links.pack(fill="x", **pad)
        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="画质：").pack(side="left")
        self.cmb_quality = ttk.Combobox(row, values=list(QUALITY_LABELS), state="readonly", width=16)
        self.cmb_quality.set(self.settings.get("quality_label", "最高清（best）"))
        self.cmb_quality.pack(side="left", padx=4)
        ttk.Label(row, text="一条推文多条视频时全部下载", foreground="#666").pack(side="left", padx=8)
        row2 = ttk.Frame(self)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text="保存到：").pack(side="left")
        self.ent_out = ttk.Entry(row2)
        self.ent_out.insert(0, self.settings.get("out_dir", os.path.join(APP_DIR, "downloads")))
        self.ent_out.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row2, text="浏览…", command=self._pick_out).pack(side="left")
        row3 = ttk.Frame(self)
        row3.pack(fill="x", **pad)
        self.btn_dl = ttk.Button(row3, text="开始下载", command=self._start_download)
        self.btn_dl.pack(side="left")
        ttk.Button(row3, text="打开保存文件夹", command=lambda: open_folder(self.ent_out.get())).pack(side="left", padx=8)
        ttk.Button(row3, text="清空输入", command=lambda: self.txt_links.delete("1.0", "end")).pack(side="left")

        self.lbl_status = ttk.Label(self, text="就绪")
        self.lbl_status.pack(anchor="w", **pad)
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.pack(fill="x", **pad)
        ttk.Label(self, text="日志：").pack(anchor="w", padx=10)
        self.txt_log = scrolledtext.ScrolledText(self, height=12, font=("Consolas", 9), state="disabled")
        self.txt_log.pack(fill="both", expand=True, **pad)
        ttk.Label(self, text="仅下载公开推文，请尊重原作者版权。", foreground="#999").pack(anchor="w", padx=10, pady=2)

    # ---------- 事件 ----------
    def _pick_out(self):
        d = filedialog.askdirectory(initialdir=self.ent_out.get() or APP_DIR)
        if d:
            self.ent_out.delete(0, "end")
            self.ent_out.insert(0, d)

    def _persist(self):
        self.settings.update({
            "out_dir": self.ent_out.get(),
            "quality_label": self.cmb_quality.get(),
        })
        save_settings(self.settings)

    def _set_busy(self, busy):
        self.busy = busy
        self.btn_dl.config(state="disabled" if busy else "normal")
        if not busy:
            self.progress["value"] = 0

    def _start_download(self):
        if self.busy:
            return
        blob = self.txt_links.get("1.0", "end").strip()
        if not blob:
            messagebox.showinfo("提示", "先粘贴至少一个链接。")
            return
        self._persist()
        self._set_busy(True)
        self.lbl_status.config(text="开始下载…")
        args = (blob, self.ent_out.get(), QUALITY_LABELS.get(self.cmb_quality.get(), "best"))
        threading.Thread(target=self._run, args=(app_core.run_downloads, args), daemon=True).start()

    # ---------- 线程桥 ----------
    def _run(self, fn, args):
        def on_line(s):
            self.q.put(("line", s))

        def on_progress(p):
            self.q.put(("progress", p))

        def on_status(s):
            self.q.put(("status", s))

        try:
            fn(*args, on_line, on_progress, on_status)
        except Exception as e:
            self.q.put(("line", "✗ 出错：%s" % e))
        finally:
            self.q.put(("done", None))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "line":
                    self.txt_log.config(state="normal")
                    self.txt_log.insert("end", val + "\n")
                    self.txt_log.see("end")
                    self.txt_log.config(state="disabled")
                elif kind == "progress":
                    self.progress["value"] = val
                elif kind == "status":
                    self.lbl_status.config(text=val)
                elif kind == "done":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(100, self._poll)


if __name__ == "__main__":
    # 打包成 windowed exe 时 sys.stdout 可能为 None，给引擎的 print 兜个底
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    App().mainloop()
