#!/usr/bin/env python3
"""CAN Bootloader GUI — flash + BMS cell monitor (DBC decode)."""

from __future__ import annotations

import io
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bl_protocol import F103_APP_MAX_SIZE, F407VE_APP_MAX_SIZE, F407VE_APP_START
from bms_monitor import BmsDbcDecoder, CanBmsMonitor, NUM_CELLS, NUM_TEMPS, find_dbc_path
from flash_can import FlashOptions, find_hex2bin, flash_image, hex_to_bin, repo_root

PCAN_INTERFACE = "pcan"


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def _fmt_mv(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f}"


def _fmt_temp(t: float | None) -> str:
    return "—" if t is None else f"{t:.1f}"


class QueueLogWriter(io.TextIOBase):
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        self._queue = log_queue

    def write(self, s: str) -> int:
        if s:
            self._queue.put(s)
        return len(s)

    def flush(self) -> None:
        pass


class GuiProgress:
    def __init__(self, ui_queue: queue.Queue[tuple]) -> None:
        self._queue = ui_queue
        self._write_t0: float | None = None
        self._last_write_notify = 0.0
        self._min_write_interval_s = 0.25

    def set_stage(self, stage: str, pct: float | None = None, detail: str = "") -> None:
        self._queue.put(("stage", stage, pct, detail))

    def begin_write(self) -> None:
        self._write_t0 = time.monotonic()
        self._last_write_notify = 0.0
        self._queue.put(("stage", "写入", 8.0, ""))

    def set_write(self, done: int, total: int) -> None:
        now = time.monotonic()
        if done < total and (now - self._last_write_notify) < self._min_write_interval_s:
            return
        self._last_write_notify = now
        total = max(total, 1)
        frac = min(1.0, max(0.0, done / total))
        pct = 8.0 + 88.0 * frac
        eta = ""
        if self._write_t0 and done > 0:
            elapsed = now - self._write_t0
            remain = elapsed * (total - done) / done
            if remain < 60:
                eta = f"  剩余 {remain:.0f}s"
            else:
                m, s = divmod(int(remain), 60)
                eta = f"  剩余 {m}m{s:02d}s"
        self._queue.put(("write", pct, done, total, eta))

    def finish(self, ok: bool, message: str = "") -> None:
        self._queue.put(("finish", ok, message))

    def close(self) -> None:
        pass


class FlashGuiApp:
    TARGETS = {
        "F407VE": {"max_size": F407VE_APP_MAX_SIZE, "hex_floor": F407VE_APP_START},
        "F103C8": {"max_size": F103_APP_MAX_SIZE, "hex_floor": None},
    }

    PCAN_CHANNELS = ["PCAN_USBBUS1", "PCAN_USBBUS2", "PCAN_USBBUS3", "PCAN_USBBUS4"]

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CAN Bootloader / BMS 工具")
        self.root.minsize(820, 720)
        self.root.geometry("960x860")

        self._ui_queue: queue.Queue[tuple] = queue.Queue()
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._flash_running = False
        self._monitor_running = False

        self.firmware_var = tk.StringVar()
        self.target_var = tk.StringVar(value="F407VE")
        self.channel_var = tk.StringVar(value="PCAN_USBBUS1")
        self.bitrate_var = tk.StringVar(value="500000")
        self.skip_rtc_var = tk.BooleanVar(value=False)
        self.no_jump_var = tk.BooleanVar(value=False)
        self.keep_bin_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)

        self.stage_var = tk.StringVar(value="就绪")
        self.detail_var = tk.StringVar(value="")
        self.pct_var = tk.StringVar(value="0%")
        self.file_info_var = tk.StringVar(value="未选择固件")

        self.monitor_status_var = tk.StringVar(value="未监听")
        self.monitor_summary_var = tk.StringVar(value="")
        self.dbc_info_var = tk.StringVar(value="")

        self._decoder: BmsDbcDecoder | None = None
        self._can_monitor: CanBmsMonitor | None = None
        self._cell_rows: dict[int, str] = {}

        self._build_ui()
        self._init_monitor()
        self._poll_queues()
        self._check_hex2bin()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 4}
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self._build_can_bar(outer, pad)

        nb = ttk.Notebook(outer)
        nb.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        flash_tab = ttk.Frame(nb, padding=4)
        monitor_tab = ttk.Frame(nb, padding=4)
        nb.add(flash_tab, text="固件烧录")
        nb.add(monitor_tab, text="电芯监控")

        self._build_flash_tab(flash_tab, pad)
        self._build_monitor_tab(monitor_tab, pad)

    def _build_can_bar(self, parent: ttk.Frame, pad: dict) -> None:
        can = ttk.LabelFrame(parent, text="PCAN 接口（烧录 / 监控共用）", padding=8)
        can.pack(fill=tk.X, **pad)
        grid = ttk.Frame(can)
        grid.pack(fill=tk.X)
        ttk.Label(grid, text="通道").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Combobox(
            grid,
            textvariable=self.channel_var,
            values=self.PCAN_CHANNELS,
            width=18,
        ).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(grid, text="波特率").grid(row=0, column=2, sticky=tk.W, padx=(16, 8))
        ttk.Entry(grid, textvariable=self.bitrate_var, width=10).grid(row=0, column=3, sticky=tk.W)
        ttk.Label(can, text="需安装 Peak PCAN-Basic 驱动", foreground="#666").pack(anchor=tk.W, pady=(6, 0))

    def _build_flash_tab(self, frm: ttk.Frame, pad: dict) -> None:
        fw = ttk.LabelFrame(frm, text="固件", padding=8)
        fw.pack(fill=tk.X, **pad)
        row = ttk.Frame(fw)
        row.pack(fill=tk.X)
        ttk.Entry(row, textvariable=self.firmware_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(row, text="浏览…", command=self._browse_firmware).pack(side=tk.LEFT)
        ttk.Label(fw, textvariable=self.file_info_var, foreground="#555").pack(anchor=tk.W, pady=(6, 0))

        tgt = ttk.LabelFrame(frm, text="目标芯片", padding=8)
        tgt.pack(fill=tk.X, **pad)
        for name in self.TARGETS:
            ttk.Radiobutton(
                tgt,
                text=f"{name}  (max {_fmt_bytes(self.TARGETS[name]['max_size'])})",
                variable=self.target_var,
                value=name,
                command=self._on_target_change,
            ).pack(anchor=tk.W)

        opt = ttk.LabelFrame(frm, text="选项", padding=8)
        opt.pack(fill=tk.X, **pad)
        ttk.Checkbutton(opt, text="跳过 RTC 同步", variable=self.skip_rtc_var).pack(anchor=tk.W)
        ttk.Checkbutton(opt, text="烧录后不跳转 APP", variable=self.no_jump_var).pack(anchor=tk.W)
        ttk.Checkbutton(
            opt, text="保留已有 .bin（hex 未更新时不重新转换）", variable=self.keep_bin_var
        ).pack(anchor=tk.W)
        ttk.Checkbutton(opt, text="Dry-run（不打开 CAN，模拟应答）", variable=self.dry_run_var).pack(anchor=tk.W)

        prog = ttk.LabelFrame(frm, text="进度", padding=8)
        prog.pack(fill=tk.X, **pad)
        top = ttk.Frame(prog)
        top.pack(fill=tk.X)
        ttk.Label(top, textvariable=self.pct_var, font=("Segoe UI", 18, "bold")).pack(side=tk.LEFT)
        ttk.Label(top, textvariable=self.stage_var).pack(side=tk.LEFT, padx=(12, 0))
        self.progress_bar = ttk.Progressbar(prog, mode="determinate", maximum=1000)
        self.progress_bar.pack(fill=tk.X, pady=(4, 4))
        ttk.Label(prog, textvariable=self.detail_var, foreground="#444").pack(anchor=tk.W)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        self.start_btn = ttk.Button(btn_row, text="开始烧录", command=self._start_flash)
        self.start_btn.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=(8, 0))

        log_frm = ttk.LabelFrame(frm, text="日志", padding=8)
        log_frm.pack(fill=tk.BOTH, expand=True, **pad)
        self.log_text = tk.Text(log_frm, height=8, wrap=tk.WORD, font=("Consolas", 9))
        scroll = ttk.Scrollbar(log_frm, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_monitor_tab(self, frm: ttk.Frame, pad: dict) -> None:
        top = ttk.Frame(frm)
        top.pack(fill=tk.X, **pad)
        self.monitor_start_btn = ttk.Button(top, text="开始监听", command=self._start_monitor)
        self.monitor_start_btn.pack(side=tk.LEFT)
        self.monitor_stop_btn = ttk.Button(top, text="停止", command=self._stop_monitor, state=tk.DISABLED)
        self.monitor_stop_btn.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(top, textvariable=self.monitor_status_var, foreground="#333").pack(side=tk.LEFT, padx=(16, 0))
        ttk.Label(frm, textvariable=self.dbc_info_var, foreground="#555").pack(anchor=tk.W, padx=10)

        summary = ttk.LabelFrame(frm, text="汇总（DBC: BMS_HCU_MAXV / MAXT）", padding=8)
        summary.pack(fill=tk.X, **pad)
        ttk.Label(summary, textvariable=self.monitor_summary_var, font=("Segoe UI", 10)).pack(anchor=tk.W)

        table_frm = ttk.LabelFrame(frm, text=f"单体数据（{NUM_CELLS} 节电压 + {NUM_TEMPS} 路温度）", padding=4)
        table_frm.pack(fill=tk.BOTH, expand=True, **pad)

        cols = ("cell", "volt", "temp")
        self.cell_tree = ttk.Treeview(table_frm, columns=cols, show="headings", height=22)
        self.cell_tree.heading("cell", text="序号")
        self.cell_tree.heading("volt", text="电压 (mV)")
        self.cell_tree.heading("temp", text="温度 (°C)")
        self.cell_tree.column("cell", width=60, anchor=tk.CENTER)
        self.cell_tree.column("volt", width=100, anchor=tk.E)
        self.cell_tree.column("temp", width=100, anchor=tk.E)

        vsb = ttk.Scrollbar(table_frm, orient=tk.VERTICAL, command=self.cell_tree.yview)
        self.cell_tree.configure(yscrollcommand=vsb.set)
        self.cell_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        for i in range(1, NUM_CELLS + 1):
            temp = _fmt_temp(None) if i > NUM_TEMPS else _fmt_temp(None)
            iid = self.cell_tree.insert("", tk.END, values=(i, "—", temp if i <= NUM_TEMPS else "—"))
            self._cell_rows[i] = iid

    def _init_monitor(self) -> None:
        try:
            dbc = find_dbc_path()
            self._decoder = BmsDbcDecoder(dbc)
            self._can_monitor = CanBmsMonitor(self._decoder)
            self.dbc_info_var.set(f"DBC: {dbc.name}  ({self._decoder.message_count} messages)")
        except FileNotFoundError as exc:
            self.dbc_info_var.set(f"DBC 未找到: {exc}")
            self.monitor_start_btn.configure(state=tk.DISABLED)

    def _check_hex2bin(self) -> None:
        try:
            exe = find_hex2bin()
            self._append_log(f"hex2bin: {exe}\n")
        except FileNotFoundError as exc:
            self._append_log(f"警告: {exc}\n")
            messagebox.showwarning("hex2bin", str(exc))

    def _on_target_change(self) -> None:
        self._update_file_info()

    def _browse_firmware(self) -> None:
        path = filedialog.askopenfilename(
            title="选择固件",
            initialdir=str(repo_root()),
            filetypes=[
                ("固件", "*.hex *.bin *.HEX *.BIN"),
                ("Intel HEX", "*.hex *.HEX"),
                ("Binary", "*.bin *.BIN"),
                ("All", "*.*"),
            ],
        )
        if path:
            self.firmware_var.set(path)
            self._update_file_info()

    def _update_file_info(self) -> None:
        raw = self.firmware_var.get().strip()
        if not raw:
            self.file_info_var.set("未选择固件")
            return
        p = Path(raw)
        if not p.is_file():
            self.file_info_var.set("文件不存在")
            return
        tgt = self.TARGETS[self.target_var.get()]
        size = p.stat().st_size
        ok = size <= tgt["max_size"]
        self.file_info_var.set(
            f"{p.name}  {_fmt_bytes(size)}  "
            f"{'✓ 大小 OK' if ok else f'✗ 超过上限 {_fmt_bytes(tgt['max_size'])}'}"
        )

    def _append_log(self, text: str) -> None:
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _resolve_bin_path(self) -> Path:
        raw = self.firmware_var.get().strip()
        if not raw:
            raise ValueError("请选择固件文件")
        path = Path(raw).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        tgt = self.TARGETS[self.target_var.get()]
        if path.suffix.lower() == ".hex":
            return hex_to_bin(path, force=not self.keep_bin_var.get(), floor_addr=tgt["hex_floor"])
        return path

    def _parse_bitrate(self) -> int:
        return int(self.bitrate_var.get().strip(), 0)

    def _can_params(self) -> tuple[str, str, int]:
        channel = self.channel_var.get().strip() or self.PCAN_CHANNELS[0]
        return PCAN_INTERFACE, channel, self._parse_bitrate()

    def _start_flash(self) -> None:
        if self._flash_running:
            return
        if self._monitor_running:
            messagebox.showwarning("占用", "请先停止电芯监控，再烧录（同一 CAN 通道不能同时打开）")
            return
        try:
            bin_path = self._resolve_bin_path()
            self._can_params()  # validate bitrate early
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("固件错误", str(exc))
            return

        tgt = self.TARGETS[self.target_var.get()]
        size = bin_path.stat().st_size
        if size > tgt["max_size"]:
            messagebox.showerror("固件过大", f"镜像超过 {self.target_var.get()} 上限")
            return

        iface, channel, bitrate = self._can_params()
        opts = FlashOptions(
            bin_path=bin_path,
            interface=iface,
            channel=channel,
            bitrate=bitrate,
            dry_run=self.dry_run_var.get(),
            no_jump=self.no_jump_var.get(),
            no_set_rtc=self.skip_rtc_var.get(),
            max_size=tgt["max_size"],
        )

        self._flash_running = True
        self.start_btn.configure(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        self.pct_var.set("0%")
        self.stage_var.set("准备")
        self.detail_var.set(bin_path.name)
        self._append_log(f"\n--- 开始烧录 {bin_path.name} ({_fmt_bytes(size)}) ---\n")

        progress = GuiProgress(self._ui_queue)

        def worker() -> None:
            old_out, old_err = sys.stdout, sys.stderr
            writer = QueueLogWriter(self._log_queue)
            sys.stdout = writer
            sys.stderr = writer
            try:
                flash_image(opts, ui=progress)
                self._ui_queue.put(("done", 0))
            except Exception as exc:
                self._ui_queue.put(("done", 1, str(exc)))
            finally:
                sys.stdout, sys.stderr = old_out, old_err

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _start_monitor(self) -> None:
        if self._monitor_running or self._decoder is None or self._can_monitor is None:
            return
        if self._flash_running:
            messagebox.showwarning("占用", "烧录进行中，请先等待完成")
            return
        try:
            iface, channel, bitrate = self._can_params()
        except ValueError:
            messagebox.showerror("参数错误", "波特率必须是整数")
            return

        self._can_monitor.start(iface, channel, bitrate)
        self.root.after(400, self._check_monitor_started)

    def _check_monitor_started(self) -> None:
        if self._can_monitor is None:
            return
        if self._can_monitor.error:
            messagebox.showerror("CAN 打开失败", self._can_monitor.error)
            self._stop_monitor()
            return
        if self._can_monitor.running:
            self._monitor_running = True
            self.monitor_status_var.set("监听中…")
            self.monitor_start_btn.configure(state=tk.DISABLED)
            self.monitor_stop_btn.configure(state=tk.NORMAL)
        else:
            self.root.after(200, self._check_monitor_started)

    def _stop_monitor(self) -> None:
        if self._can_monitor is not None:
            self._can_monitor.stop()
        self._monitor_running = False
        self.monitor_status_var.set("已停止")
        self.monitor_start_btn.configure(state=tk.NORMAL)
        self.monitor_stop_btn.configure(state=tk.DISABLED)

    def _refresh_cell_table(self) -> None:
        if self._decoder is None:
            return
        snap = self._decoder.snapshot()
        min_no = snap.min_cell_no
        max_no = snap.max_cell_no

        for i in range(1, NUM_CELLS + 1):
            mv = snap.cell_mv[i - 1]
            iid = self._cell_rows[i]
            temp_str = _fmt_temp(snap.temp_c[i - 1]) if i <= NUM_TEMPS else "—"
            self.cell_tree.item(iid, values=(i, _fmt_mv(mv), temp_str))
            if mv is not None and i == max_no:
                self.cell_tree.tag_configure("max", background="#ffe0e0")
                self.cell_tree.item(iid, tags=("max",))
            elif mv is not None and i == min_no:
                self.cell_tree.tag_configure("min", background="#e0f0ff")
                self.cell_tree.item(iid, tags=("min",))
            else:
                self.cell_tree.item(iid, tags=())

        parts = []
        if snap.max_cell_mv is not None and snap.max_cell_no is not None:
            parts.append(f"最高 {snap.max_cell_mv:.0f} mV (#{snap.max_cell_no})")
        if snap.min_cell_mv is not None and snap.min_cell_no is not None:
            parts.append(f"最低 {snap.min_cell_mv:.0f} mV (#{snap.min_cell_no})")
        if snap.max_temp_c is not None and snap.max_temp_no is not None:
            parts.append(f"最高温 {snap.max_temp_c:.1f} °C (#{snap.max_temp_no})")
        if snap.min_temp_c is not None and snap.min_temp_no is not None:
            parts.append(f"最低温 {snap.min_temp_c:.1f} °C (#{snap.min_temp_no})")
        if snap.last_update:
            age = max(0.0, time.time() - snap.last_update)
            parts.append(f"帧 {snap.frames_decoded}  更新 {age:.1f}s 前")
        self.monitor_summary_var.set("  |  ".join(parts) if parts else "等待 CAN 数据…")

    def _poll_queues(self) -> None:
        while True:
            try:
                msg = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(msg)

        while True:
            try:
                msg = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_ui_msg(msg)

        if self._monitor_running:
            self._refresh_cell_table()

        self.root.after(250 if self._monitor_running else 80, self._poll_queues)

    def _handle_ui_msg(self, msg: tuple) -> None:
        kind = msg[0]
        if kind == "stage":
            _, stage, pct, detail = msg
            self.stage_var.set(stage)
            if pct is not None:
                self.pct_var.set(f"{pct:.1f}%")
                self.progress_bar["value"] = int(pct * 10)
            if detail:
                self.detail_var.set(detail)
        elif kind == "write":
            _, pct, done, total, eta = msg
            self.pct_var.set(f"{pct:.1f}%")
            self.progress_bar["value"] = int(pct * 10)
            self.stage_var.set("写入")
            self.detail_var.set(f"{done} / {total} 字节{eta}")
        elif kind == "finish":
            _, ok, message = msg
            if ok:
                self.pct_var.set("100%")
                self.progress_bar["value"] = 1000
                self.stage_var.set("完成")
                self.detail_var.set(message or "烧录完成")
            else:
                self.stage_var.set("失败")
                self.detail_var.set(message)
        elif kind == "done":
            self._flash_running = False
            self.start_btn.configure(state=tk.NORMAL)
            if msg[1] == 0:
                messagebox.showinfo("完成", "烧录成功")
            else:
                messagebox.showerror("失败", msg[2] if len(msg) > 2 else "烧录失败")

    def on_close(self) -> None:
        self._stop_monitor()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    app = FlashGuiApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
