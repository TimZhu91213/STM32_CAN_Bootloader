#!/usr/bin/env python3
"""Popup percentage window for flash_can.py — file-based IPC, never blocks flasher."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional


def _fmt_sec(sec: float) -> str:
    sec = max(0.0, sec)
    if sec < 60.0:
        return f"{sec:.0f}s"
    m, s = divmod(int(sec), 60)
    return f"{m}m{s:02d}s"


def _default_state(image_name: str, image_size: int) -> dict[str, Any]:
    return {
        "name": image_name,
        "size": image_size,
        "pct": 0.0,
        "stage": "启动",
        "detail": "",
        "done": 0,
        "total": max(image_size, 1),
        "done_flag": False,
        "ok": None,
        "message": "",
    }


def _run_window(state_path: Path) -> None:
    import tkinter as tk
    from tkinter import ttk

    state_path = state_path.resolve()
    snap = _default_state("?", 0)

    win_w, win_h = 480, 220

    root = tk.Tk()
    root.title("CAN 烧录进度")
    root.resizable(True, True)
    root.minsize(420, 200)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    root.geometry(f"{win_w}x{win_h}")
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{win_w}x{win_h}+{max(0, (sw - win_w) // 2)}+{max(0, (sh - win_h) // 3)}")

    frm = ttk.Frame(root, padding=14)
    frm.pack(fill=tk.BOTH, expand=True)

    title_lbl = ttk.Label(frm, text=snap["name"], font=("Segoe UI", 11, "bold"))
    title_lbl.pack(anchor="w")
    size_lbl = ttk.Label(frm, text="", foreground="#555")
    size_lbl.pack(anchor="w", pady=(0, 8))

    pct_var = tk.StringVar(value="0%")
    pct_lbl = ttk.Label(frm, textvariable=pct_var, font=("Segoe UI", 22, "bold"))
    pct_lbl.pack(anchor="w")
    bar = ttk.Progressbar(frm, mode="determinate", maximum=1000)
    bar.pack(fill=tk.X, expand=True, pady=(4, 8))
    stage_var = tk.StringVar(value="启动")
    ttk.Label(frm, textvariable=stage_var).pack(anchor="w")
    detail_var = tk.StringVar(value="")
    ttk.Label(frm, textvariable=detail_var, foreground="#444").pack(anchor="w")

    ui = {"allow_close": False, "quit_at": None}

    def apply_state(data: dict[str, Any]) -> None:
        name = str(data.get("name", snap.get("name", "?")))
        size = int(data.get("size", 0))
        pct = max(0.0, min(100.0, float(data.get("pct", 0.0))))
        stage = str(data.get("stage", ""))
        detail = str(data.get("detail", ""))
        done_flag = bool(data.get("done_flag"))
        ok = data.get("ok")

        title_lbl.configure(text=name)
        size_lbl.configure(text=f"{size} 字节  ({size / 1024.0:.1f} KB)")
        pct_var.set(f"{pct:.1f}%")
        bar["value"] = int(pct * 10.0)
        if stage:
            stage_var.set(stage)
        detail_var.set(detail)

        if done_flag and ok is not None and not ui["allow_close"]:
            ui["allow_close"] = True
            ui["quit_at"] = time.monotonic() + (2.5 if ok else 8.0)
            pct_lbl.configure(foreground="#1b7f1b" if ok else "#b00020")

    def on_close() -> None:
        if ui["allow_close"]:
            root.quit()

    root.protocol("WM_DELETE_WINDOW", on_close)

    def poll() -> None:
        nonlocal snap
        if state_path.is_file():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                snap = data
                apply_state(data)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        elif not state_path.exists():
            root.quit()
            return

        quit_at = ui["quit_at"]
        if quit_at is not None and time.monotonic() >= quit_at:
            root.quit()
            return
        root.after(120, poll)

    apply_state(snap)
    root.after(120, poll)
    root.mainloop()
    try:
        root.destroy()
    except Exception:
        pass


class FlashProgressUI:
    """Fire-and-forget progress file updates; CAN flasher never waits on UI."""

    _MIN_WRITE_INTERVAL_S = 0.5

    def __init__(self, image_name: str, image_size: int) -> None:
        self._name = image_name
        self._size = image_size
        self._proc: Optional[subprocess.Popen] = None
        self._state_path = Path(tempfile.gettempdir()) / f"can_flash_{os.getpid()}_{time.time_ns()}.json"
        self._state: dict[str, Any] = _default_state(image_name, image_size)
        self._write_t0: Optional[float] = None
        self._last_write_notify = 0.0
        self._last_persist = 0.0
        self._lock = threading.Lock()

    @property
    def state_path(self) -> Path:
        return self._state_path

    def start(self, timeout_s: float = 2.0) -> bool:
        self._persist(force=True)
        script = Path(__file__).resolve()
        exe = sys.executable
        if sys.platform == "win32":
            pythonw = Path(exe).with_name("pythonw.exe")
            if pythonw.is_file():
                exe = str(pythonw)
        kwargs: dict = {
            "args": [exe, str(script), "--state-file", str(self._state_path)],
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._proc = subprocess.Popen(**kwargs)
        except OSError:
            return False
        time.sleep(min(0.25, timeout_s))
        return self._proc.poll() is None

    def _persist(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_persist) < 0.08:
            return
        self._last_persist = now
        try:
            self._state_path.write_text(
                json.dumps(self._state, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def set_stage(self, stage: str, pct: float | None = None, detail: str = "") -> None:
        with self._lock:
            self._state["stage"] = stage
            if pct is not None:
                self._state["pct"] = max(0.0, min(100.0, pct))
            if detail:
                self._state["detail"] = detail
        self._persist(force=True)

    def begin_write(self) -> None:
        self._write_t0 = time.monotonic()
        self._last_write_notify = 0.0
        with self._lock:
            self._state["stage"] = "写入"
            self._state["pct"] = 8.0
            self._state["done"] = 0
            self._state["total"] = max(self._size, 1)
        self._persist(force=True)

    def set_write(self, done: int, total: int) -> None:
        now = time.monotonic()
        if done < total and (now - self._last_write_notify) < self._MIN_WRITE_INTERVAL_S:
            return
        self._last_write_notify = now
        total = max(total, 1)
        frac = min(1.0, max(0.0, done / total))
        pct = 8.0 + 88.0 * frac
        eta = ""
        if self._write_t0 and done > 0:
            elapsed = now - self._write_t0
            remain = elapsed * (total - done) / done
            eta = f"  剩余 {_fmt_sec(remain)}"
        with self._lock:
            self._state["stage"] = "写入"
            self._state["pct"] = pct
            self._state["done"] = done
            self._state["total"] = total
            self._state["detail"] = f"{done} / {total} 字节{eta}"
        self._persist()

    def finish(self, ok: bool, message: str = "") -> None:
        with self._lock:
            self._state["done_flag"] = True
            self._state["ok"] = ok
            self._state["stage"] = "完成" if ok else "失败"
            self._state["message"] = message
            if message:
                self._state["detail"] = message
            if ok:
                self._state["pct"] = 100.0
        self._persist(force=True)

    def close(self) -> None:
        proc = self._proc
        if proc is not None:
            try:
                proc.wait(timeout=12.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            self._proc = None
        try:
            self._state_path.unlink(missing_ok=True)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CAN flash progress window")
    p.add_argument("--state-file", type=Path, required=True)
    args = p.parse_args(argv or sys.argv[1:])
    _run_window(args.state_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
