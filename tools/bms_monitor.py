#!/usr/bin/env python3
"""Decode BMS cell voltage/temperature frames from FSAE CHD DBC."""

from __future__ import annotations

import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cantools

from flash_can import app_dir, repo_root
from can_backend import open_can_bus

CELL_V_RE = re.compile(r"^Cell(\d+)_mV$")
TEMP_RE = re.compile(r"^Temp(\d+)_degC$")

NUM_CELLS = 108
NUM_TEMPS = 54


def find_dbc_path() -> Path:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "FSAE_CHD_BMS_CAN_Protocol_V0.2.dbc")
        candidates.append(app_dir() / "FSAE_CHD_BMS_CAN_Protocol_V0.2.dbc")
    root = repo_root()
    candidates.extend(
        [
            root / "FSAE_CHD_BMS_CAN_Protocol_V0.2.dbc",
            root.parent / "FSAE_CHD_BMS_CAN_Protocol_V0.2.dbc",
            Path(__file__).resolve().parent / "FSAE_CHD_BMS_CAN_Protocol_V0.2.dbc",
        ]
    )
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand.resolve()
    raise FileNotFoundError(
        "FSAE_CHD_BMS_CAN_Protocol_V0.2.dbc not found (expected in repo root or beside the app)"
    )


@dataclass
class BmsSnapshot:
    cell_mv: list[float | None] = field(default_factory=lambda: [None] * NUM_CELLS)
    temp_c: list[float | None] = field(default_factory=lambda: [None] * NUM_TEMPS)
    max_cell_mv: float | None = None
    min_cell_mv: float | None = None
    max_cell_no: int | None = None
    min_cell_no: int | None = None
    max_temp_c: float | None = None
    min_temp_c: float | None = None
    max_temp_no: int | None = None
    min_temp_no: int | None = None
    frames_decoded: int = 0
    last_update: float = 0.0

    def copy(self) -> BmsSnapshot:
        return BmsSnapshot(
            cell_mv=list(self.cell_mv),
            temp_c=list(self.temp_c),
            max_cell_mv=self.max_cell_mv,
            min_cell_mv=self.min_cell_mv,
            max_cell_no=self.max_cell_no,
            min_cell_no=self.min_cell_no,
            max_temp_c=self.max_temp_c,
            min_temp_c=self.min_temp_c,
            max_temp_no=self.max_temp_no,
            min_temp_no=self.min_temp_no,
            frames_decoded=self.frames_decoded,
            last_update=self.last_update,
        )


class BmsDbcDecoder:
    """Parse BMS extended CAN frames using cantools + DBC."""

    def __init__(self, dbc_path: Path | None = None) -> None:
        path = dbc_path or find_dbc_path()
        self.dbc_path = path
        self.db = cantools.database.load_file(str(path))
        self._by_id = {m.frame_id: m for m in self.db.messages}
        self._lock = threading.Lock()
        self._snap = BmsSnapshot()

    @property
    def message_count(self) -> int:
        return len(self.db.messages)

    def snapshot(self) -> BmsSnapshot:
        with self._lock:
            return self._snap.copy()

    def handle_frame(self, can_id: int, data: bytes) -> bool:
        msg = self._by_id.get(can_id)
        if msg is None:
            return False
        try:
            decoded: dict[str, Any] = msg.decode(data, decode_choices=False)
        except Exception:
            return False

        now = time.time()
        with self._lock:
            self._snap.frames_decoded += 1
            self._snap.last_update = now
            name = msg.name
            if name.startswith("BMS_CELL_V_"):
                for sig, val in decoded.items():
                    m = CELL_V_RE.match(sig)
                    if m:
                        idx = int(m.group(1)) - 1
                        if 0 <= idx < NUM_CELLS:
                            self._snap.cell_mv[idx] = float(val)
            elif name.startswith("BMS_CELL_T_"):
                for sig, val in decoded.items():
                    m = TEMP_RE.match(sig)
                    if m:
                        idx = int(m.group(1)) - 1
                        if 0 <= idx < NUM_TEMPS:
                            self._snap.temp_c[idx] = float(val)
            elif name == "BMS_HCU_MAXV":
                self._snap.max_cell_mv = _f(decoded.get("MaxCellVolt"))
                self._snap.min_cell_mv = _f(decoded.get("MinCellVolt"))
                self._snap.max_cell_no = _i(decoded.get("MaxCellVoltNo"))
                self._snap.min_cell_no = _i(decoded.get("MinCellVoltNo"))
            elif name == "BMS_HCU_MAXT":
                self._snap.max_temp_c = _f(decoded.get("MaxTemp"))
                self._snap.min_temp_c = _f(decoded.get("MinTemp"))
                self._snap.max_temp_no = _i(decoded.get("MaxTempNo"))
                self._snap.min_temp_no = _i(decoded.get("MinTempNo"))
        return True


def _f(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _i(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


class CanBmsMonitor:
    """Background CAN listener that fills a BmsDbcDecoder."""

    def __init__(self, decoder: BmsDbcDecoder) -> None:
        self.decoder = decoder
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._bus = None
        self.error: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, interface: str, channel: str, bitrate: int, app_name: str | None = None) -> None:
        if self.running:
            return
        self.error = None
        self._stop.clear()

        def worker() -> None:
            try:
                self._bus = open_can_bus(
                    interface=interface,
                    channel=channel,
                    bitrate=bitrate,
                    app_name=app_name,
                )
            except Exception as exc:
                self.error = str(exc)
                return
            while not self._stop.is_set():
                try:
                    msg = self._bus.recv(timeout=0.25)
                except Exception as exc:
                    self.error = str(exc)
                    break
                if msg is None:
                    continue
                self.decoder.handle_frame(msg.arbitration_id, bytes(msg.data))

        self._thread = threading.Thread(target=worker, daemon=True, name="CanBmsMonitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._bus is not None:
            try:
                self._bus.shutdown()
            except Exception:
                pass
            self._bus = None
        th = self._thread
        if th is not None:
            th.join(timeout=2.0)
            self._thread = None
