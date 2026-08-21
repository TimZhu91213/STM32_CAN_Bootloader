#!/usr/bin/env python3
"""
CAN bootloader host flasher (F103 first; params portable).

Flow (mirrors DieBieMS erase -> write chunks -> jump):
  1) GET_INFO handshake
  2) SET_RTC (PC local time, optional --no-set-rtc)
  3) ERASE(image_size)
  4) SET_ADDR(0) + WRITE_DATA stream
  5) CRC(image)
  6) JUMP_APP

Examples:
  python flash_can.py --bin app.bin --interface pcan --channel PCAN_USBBUS1
  python flash_can.py --hex ../F407_VET6_Test.hex --max-size 507904
  python flash_can.py --image CHU_BMS_F407VET6 --max-size 507904
  python flash_can.py --bin _test_app.bin --send-only
  python flash_can.py --bin app.bin --dry-run
  python flash_can.py --bin app.bin --no-progress-window
"""

from __future__ import annotations

import argparse
import datetime
import struct
import subprocess
import sys
import time
from pathlib import Path

from flash_progress import FlashProgressUI
from bl_protocol import (
    BL_CAN_ID_CMD,
    BL_CAN_ID_RSP,
    BL_CMD_ABORT,
    BL_CMD_CRC,
    BL_CMD_ERASE,
    BL_CMD_GET_INFO,
    BL_CMD_JUMP_APP,
    BL_CMD_SET_ADDR,
    BL_CMD_SET_RTC,
    BL_CMD_WRITE_DATA,
    BL_PROTOCOL_VERSION,
    BL_STATUS_ERR_UNKNOWN,
    BL_STATUS_OK,
    CHUNK_DATA_BYTES,
    F103_APP_MAX_SIZE,
    F407VE_APP_MAX_SIZE,
    STATUS_NAME,
    crc32_mpeg2_like,
    u32_le,
)


class CanTransport:
    """Thin wrapper; dry-run prints frames instead of sending."""

    def __init__(
        self,
        interface: str | None,
        channel: str | None,
        bitrate: int,
        dry_run: bool,
        verbose_tx: bool = False,
    ):
        self.dry_run = dry_run
        self.verbose_tx = verbose_tx or dry_run
        self.bus = None
        if dry_run:
            return
        import can  # type: ignore

        self.bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate)

    def close(self) -> None:
        if self.bus is not None:
            self.bus.shutdown()

    def send(self, data: bytes, can_id: int = BL_CAN_ID_CMD) -> None:
        data = bytes(data)
        if len(data) > 8:
            raise ValueError("CAN payload > 8")
        if self.verbose_tx:
            print(f"TX id=0x{can_id:03X} data={data.hex()}")
        if self.dry_run:
            return
        import can  # type: ignore

        msg = can.Message(
            arbitration_id=can_id,
            data=data,
            is_extended_id=False,
        )
        self.bus.send(msg)

    def drain(self, duration_s: float = 0.05) -> list[bytes]:
        """Flush RX queue; return any 0x701 payloads seen."""
        seen: list[bytes] = []
        if self.dry_run or self.bus is None:
            return seen
        deadline = time.time() + duration_s
        while time.time() < deadline:
            msg = self.bus.recv(timeout=max(0.0, deadline - time.time()))
            if msg is None:
                break
            if msg.arbitration_id == BL_CAN_ID_RSP:
                seen.append(bytes(msg.data))
        return seen

    def recv(self, timeout_s: float, expect_cmd: int | None = None, expect_seq: int | None = None) -> bytes | None:
        if self.dry_run:
            cmd = expect_cmd if expect_cmd is not None else BL_CMD_GET_INFO
            if cmd == BL_CMD_GET_INFO:
                return bytes(
                    [BL_CMD_GET_INFO, BL_STATUS_OK, BL_PROTOCOL_VERSION, 0, 19, 0x01, 0x00, 0x4C]
                )
            if cmd == BL_CMD_WRITE_DATA and expect_seq is not None:
                return bytes([BL_CMD_WRITE_DATA, BL_STATUS_OK, expect_seq & 0xFF, 0, 0, 0, 0, 0])
            return bytes([cmd, BL_STATUS_OK, 0, 0, 0, 0, 0, 0])

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            msg = self.bus.recv(timeout=max(0.0, deadline - time.time()))
            if msg is None:
                continue
            if msg.arbitration_id != BL_CAN_ID_RSP:
                if self.verbose_tx:
                    print(f"RX ignore id=0x{msg.arbitration_id:03X} data={bytes(msg.data).hex()}")
                continue
            payload = bytes(msg.data)
            print(f"RX 0x701 {payload.hex()}")
            if expect_cmd is not None and (not payload or payload[0] != expect_cmd):
                print(f"  (ignored, want cmd=0x{expect_cmd:02X})")
                continue
            if expect_seq is not None:
                if len(payload) < 3 or payload[2] != (expect_seq & 0xFF):
                    print(f"  (ignored, want seq={expect_seq & 0xFF})")
                    continue
            return payload
        return None


def require_ok(rsp: bytes | None, cmd: int) -> bytes:
    if rsp is None:
        raise RuntimeError(f"timeout waiting for response to cmd 0x{cmd:02X}")
    if len(rsp) < 2:
        raise RuntimeError(f"short response: {rsp.hex()}")
    status = rsp[1]
    if status != BL_STATUS_OK:
        name = STATUS_NAME.get(status, f"0x{status:02X}")
        raise RuntimeError(f"device error on cmd 0x{cmd:02X}: {name}")
    return rsp


def maybe_wait(tr: CanTransport, cmd: int, timeout: float, send_only: bool) -> None:
    if send_only:
        return
    require_ok(tr.recv(timeout, cmd), cmd)


def handshake(tr: CanTransport, timeout: float, send_only: bool) -> None:
    if send_only:
        tr.send(bytes([BL_CMD_GET_INFO]))
        print("GET_INFO sent (send-only, no wait)")
        return

    # Drop stale ABORT/old replies sitting in PCAN RX FIFO
    stale = tr.drain(0.1)
    if stale:
        print(f"drained {len(stale)} stale 0x701 frame(s): " + ", ".join(p.hex() for p in stale))

    last_err = None
    for attempt in range(1, 6):
        tr.drain(0.02)
        print(f"TX GET_INFO attempt {attempt}/5")
        tr.send(bytes([BL_CMD_GET_INFO]))
        rsp = tr.recv(max(timeout, 1.5), BL_CMD_GET_INFO)
        if rsp is not None:
            require_ok(rsp, BL_CMD_GET_INFO)
            proto = rsp[2] if len(rsp) > 2 else None
            maj = rsp[3] if len(rsp) > 3 else None
            minor = rsp[4] if len(rsp) > 4 else None
            print(f"GET_INFO ok, protocol={proto}, bl={maj}.{minor}, raw={rsp.hex()}")
            if proto is not None and proto != BL_PROTOCOL_VERSION:
                print(f"warning: protocol mismatch host={BL_PROTOCOL_VERSION} device={proto}")
            return
        last_err = f"timeout waiting for response to cmd 0x{BL_CMD_GET_INFO:02X}"
        print(f"GET_INFO attempt {attempt}/5 failed, retry...")
        time.sleep(0.5)

    print(
        "hint:\n"
        "  - Close TSMaster measurement OR use the OTHER CAN adapter only for monitor\n"
        "    (do not open the same PCAN channel in two programs).\n"
        "  - Second adapter should be Listen-Only if only used for sniffing.\n"
        "  - Confirm RX 0x701 starts with 01 (GET_INFO), not 07 (ABORT leftover)."
    )
    raise RuntimeError(last_err or "GET_INFO failed")


def set_rtc(tr: CanTransport, timeout: float, send_only: bool) -> None:
    ts = int(datetime.datetime.now().timestamp())
    when = datetime.datetime.now().replace(microsecond=0).isoformat(sep=" ")
    print(f"SET_RTC unix={ts} ({when})")
    if send_only:
        tr.send(bytes([BL_CMD_SET_RTC]) + u32_le(ts))
        print("SET_RTC sent (send-only, no wait)")
        return

    tr.send(bytes([BL_CMD_SET_RTC]) + u32_le(ts))
    rsp = tr.recv(timeout, BL_CMD_SET_RTC)
    if rsp is None:
        raise RuntimeError(f"timeout waiting for response to cmd 0x{BL_CMD_SET_RTC:02X}")
    if len(rsp) < 2:
        raise RuntimeError(f"short SET_RTC response: {rsp.hex()}")
    status = rsp[1]
    if status == BL_STATUS_OK:
        print("SET_RTC ok")
        return
    if status == BL_STATUS_ERR_UNKNOWN:
        print("warning: device BL does not support SET_RTC (ERR_UNKNOWN), continuing")
        return
    name = STATUS_NAME.get(status, f"0x{status:02X}")
    raise RuntimeError(f"device error on cmd 0x{BL_CMD_SET_RTC:02X}: {name}")


def erase(tr: CanTransport, image_size: int, timeout: float, send_only: bool) -> None:
    print(f"ERASE {image_size} bytes ...")
    if send_only:
        tr.send(bytes([BL_CMD_ERASE]) + u32_le(image_size))
        print("ERASE sent (send-only)")
        return

    erase_timeout = max(timeout, 5.0)
    for attempt in range(1, 6):
        tr.drain(0.05)
        print(f"TX ERASE attempt {attempt}/5")
        tr.send(bytes([BL_CMD_ERASE]) + u32_le(image_size))
        rsp = tr.recv(erase_timeout, BL_CMD_ERASE)
        if rsp is not None:
            require_ok(rsp, BL_CMD_ERASE)
            print("ERASE ok")
            # Let STM32 leave erase/CAN-restart fully before SET_ADDR
            time.sleep(0.25)
            stale = tr.drain(0.15)
            for p in stale:
                print(f"drained after ERASE: {p.hex()}")
            return
        print(f"ERASE attempt {attempt}/5 failed, retry...")
        time.sleep(0.3)
    raise RuntimeError("timeout waiting for response to cmd 0x02")


def set_addr(tr: CanTransport, offset: int, timeout: float, send_only: bool) -> None:
    if send_only:
        tr.send(bytes([BL_CMD_SET_ADDR]) + u32_le(offset))
        return

    for attempt in range(1, 6):
        stale = tr.drain(0.1)
        for p in stale:
            print(f"drained before SET_ADDR: {p.hex()}")
        print(f"TX SET_ADDR attempt {attempt}/5 offset={offset}")
        tr.send(bytes([BL_CMD_SET_ADDR]) + u32_le(offset))
        rsp = tr.recv(timeout, BL_CMD_SET_ADDR)
        if rsp is not None:
            require_ok(rsp, BL_CMD_SET_ADDR)
            print(f"SET_ADDR ok offset={offset}")
            tr.drain(0.05)
            return
        print(f"SET_ADDR attempt {attempt}/5 failed, retry...")
        time.sleep(0.2)
    raise RuntimeError("timeout waiting for response to cmd 0x03")


def write_image(
    tr: CanTransport,
    image: bytes,
    timeout: float,
    progress: bool,
    send_only: bool,
    gap_s: float,
    on_progress=None,
) -> None:
    set_addr(tr, 0, timeout, send_only)
    if gap_s:
        time.sleep(gap_s)
    total = len(image)
    offset = 0
    iterator = range(0, total, CHUNK_DATA_BYTES)
    if progress:
        try:
            from tqdm import tqdm

            iterator = tqdm(
                iterator,
                total=(total + CHUNK_DATA_BYTES - 1) // CHUNK_DATA_BYTES,
                unit="frm",
            )
        except Exception:
            pass

    seq = 0
    for start in iterator:
        chunk = image[start : start + CHUNK_DATA_BYTES]
        if send_only:
            tr.send(bytes([BL_CMD_WRITE_DATA, seq & 0xFF]) + chunk)
            offset += len(chunk)
            seq = (seq + 1) & 0xFF
            if on_progress is not None and (
                offset >= total or offset == len(chunk) or offset % max(total // 200, 6144) == 0
            ):
                on_progress(offset, total)
            if gap_s:
                time.sleep(gap_s)
            continue

        tr.drain(0.0)
        ok = False
        for attempt in range(1, 4):
            # [cmd=0x04][seq][data...]
            tr.send(bytes([BL_CMD_WRITE_DATA, seq & 0xFF]) + chunk)
            rsp = tr.recv(timeout, BL_CMD_WRITE_DATA, expect_seq=seq)
            if rsp is not None:
                require_ok(rsp, BL_CMD_WRITE_DATA)
                ok = True
                break
            print(f"  WRITE @{start} seq={seq} attempt {attempt}/3 failed, retry...")
            time.sleep(0.02)
        if not ok:
            raise RuntimeError(f"timeout waiting for WRITE seq={seq}")
        tr.drain(0.0)
        offset += len(chunk)
        seq = (seq + 1) & 0xFF
        if on_progress is not None and (
            offset >= total or offset == len(chunk) or offset % max(total // 200, 6144) == 0
        ):
            on_progress(offset, total)
        log_every = 4096 if on_progress is not None else 64
        if (offset == len(chunk)) or (offset % log_every == 0) or (offset >= total):
            print(f"  WRITE {offset}/{total}")
        if gap_s:
            time.sleep(gap_s)

    print(f"WRITE sent, {offset} bytes")


def verify_crc(tr: CanTransport, image: bytes, timeout: float, send_only: bool) -> None:
    crc = crc32_mpeg2_like(image)
    tr.send(bytes([BL_CMD_CRC]) + u32_le(crc))
    maybe_wait(tr, BL_CMD_CRC, timeout, send_only)
    print(f"CRC sent (0x{crc:08X})")


def jump_app(tr: CanTransport, timeout: float, send_only: bool) -> None:
    tr.send(bytes([BL_CMD_JUMP_APP]))
    if send_only:
        print("JUMP_APP sent (send-only, no wait)")
        return
    rsp = tr.recv(timeout, BL_CMD_JUMP_APP)
    if rsp is None:
        print("JUMP_APP sent (no response — device may have reset)")
    else:
        require_ok(rsp, BL_CMD_JUMP_APP)
        print("JUMP_APP ok — device jumping to application (VTOR)")


def abort_session(tr: CanTransport, timeout: float) -> None:
    tr.send(bytes([BL_CMD_ABORT]))
    tr.recv(timeout, BL_CMD_ABORT)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def find_hex2bin() -> Path:
    root = repo_root()
    for rel in (
        Path("Hex2bin-2.5") / "bin" / "Release" / "hex2bin.exe",
        Path("Hex2bin-2.5") / "bin" / "Debug" / "hex2bin.exe",
        Path("Hex2bin-2.5") / "hex2bin.exe",
    ):
        cand = root / rel
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        "hex2bin.exe not found under Hex2bin-2.5/bin/Release (or Debug)"
    )


def resolve_named_image(name: str, search_dirs: list[Path]) -> Path:
    """Resolve stem or path to an existing .hex or .bin under search_dirs / as path."""
    raw = Path(name)
    if raw.suffix.lower() in {".hex", ".bin"} and raw.is_file():
        return raw.resolve()
    if raw.is_file():
        return raw.resolve()

    stem = raw.stem if raw.suffix else raw.name
    for d in search_dirs:
        for ext in (".hex", ".bin"):
            cand = d / f"{stem}{ext}"
            if cand.is_file():
                return cand.resolve()
    raise FileNotFoundError(
        f"image '{name}' not found as .hex/.bin in: "
        + ", ".join(str(d) for d in search_dirs)
    )


def hex_to_bin(hex_path: Path, *, force: bool = True, floor_addr: int | None = None) -> Path:
    """
    Convert Intel HEX → BIN via repo Hex2bin-2.5.
    Output is <same_dir>/<stem>.bin (hex2bin default).
    Without -s, bin starts at the lowest address in the hex (correct for APP @ 0x08004000).
    """
    hex_path = hex_path.resolve()
    if not hex_path.is_file():
        raise FileNotFoundError(f"hex not found: {hex_path}")

    bin_path = hex_path.with_suffix(".bin")
    if (
        not force
        and bin_path.is_file()
        and bin_path.stat().st_mtime >= hex_path.stat().st_mtime
    ):
        print(f"hex2bin: reuse up-to-date {bin_path}")
        return bin_path

    exe = find_hex2bin()
    cmd = [str(exe)]
    if floor_addr is not None:
        cmd += ["-t", f"{floor_addr:X}"]
    cmd.append(str(hex_path))
    print(f"hex2bin: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(hex_path.parent), capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"hex2bin failed (code {proc.returncode}): {err}")
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if not bin_path.is_file():
        raise FileNotFoundError(f"hex2bin did not create {bin_path}")
    print(f"hex2bin: wrote {bin_path} ({bin_path.stat().st_size} bytes)")
    return bin_path


def resolve_flash_bin(args: argparse.Namespace) -> Path:
    """Pick .bin to flash; convert from .hex when needed."""
    search = [
        Path.cwd(),
        repo_root(),
        repo_root() / "tools",
    ]

    if args.image:
        path = resolve_named_image(args.image, search)
        if path.suffix.lower() == ".hex":
            return hex_to_bin(path, force=not args.keep_bin, floor_addr=args.hex_floor)
        return path

    if args.hex:
        hex_path = args.hex
        if not hex_path.is_file():
            hex_path = resolve_named_image(str(args.hex), search)
        if hex_path.suffix.lower() != ".hex":
            raise ValueError(f"--hex expects a .hex file, got {hex_path}")
        return hex_to_bin(hex_path, force=not args.keep_bin, floor_addr=args.hex_floor)

    if args.bin:
        bin_path = args.bin
        if bin_path.suffix.lower() == ".hex":
            return hex_to_bin(bin_path, force=not args.keep_bin, floor_addr=args.hex_floor)
        if not bin_path.is_file():
            # Same stem .hex beside missing .bin → convert
            hex_sib = bin_path.with_suffix(".hex")
            if not hex_sib.is_file():
                try:
                    hex_sib = resolve_named_image(bin_path.stem, search)
                except FileNotFoundError:
                    hex_sib = Path()
            if hex_sib.suffix.lower() == ".hex" and hex_sib.is_file():
                print(f"note: {bin_path} missing, converting {hex_sib}")
                return hex_to_bin(hex_sib, force=not args.keep_bin, floor_addr=args.hex_floor)
            raise FileNotFoundError(f"bin not found: {bin_path}")
        return bin_path.resolve()

    raise ValueError("specify --bin, --hex, or --image")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CAN bootloader flasher")
    p.add_argument(
        "--bin",
        type=Path,
        help="Application .bin (linked at APP start). If missing but .hex exists, converts it.",
    )
    p.add_argument(
        "--hex",
        type=Path,
        help="Keil Intel HEX; convert with Hex2bin-2.5 then flash the resulting .bin",
    )
    p.add_argument(
        "--image",
        type=str,
        help="Stem or path under repo (e.g. F407_VET6_Test); prefers .hex then .bin",
    )
    p.add_argument(
        "--keep-bin",
        action="store_true",
        help="Skip hex2bin if existing .bin is newer than .hex",
    )
    p.add_argument(
        "--hex-floor",
        type=lambda s: int(s, 0),
        default=None,
        help="Optional hex2bin -t floor (e.g. 0x08004000) if HEX contains lower regions",
    )
    p.add_argument("--interface", default="pcan", help="python-can interface (pcan/candlelight/socketcan/...)")
    p.add_argument("--channel", default="PCAN_USBBUS1", help="CAN channel (PCAN: PCAN_USBBUS1)")
    p.add_argument("--bitrate", type=int, default=500000, help="CAN bitrate")
    p.add_argument("--gap-ms", type=float, default=0.5, help="Delay between frames (ms, default 0.5)")
    p.add_argument("--timeout", type=float, default=3.0, help="Per-frame response timeout (s)")
    p.add_argument("--dry-run", action="store_true", help="Do not open CAN; simulate OK replies")
    p.add_argument(
        "--send-only",
        action="store_true",
        help="Open PCAN and send all frames; do not wait for device replies",
    )
    p.add_argument("--verbose", action="store_true", help="Print every TX/RX frame")
    p.add_argument("--no-jump", action="store_true", help="Skip JUMP_APP")
    p.add_argument(
        "--no-set-rtc",
        action="store_true",
        help="Skip SET_RTC after handshake (debug / boards without LSE)",
    )
    p.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable popup progress window and tqdm",
    )
    p.add_argument(
        "--no-progress-window",
        action="store_true",
        help="Do not pop up a percentage window (tqdm still allowed)",
    )
    p.add_argument(
        "--max-size",
        type=int,
        default=F103_APP_MAX_SIZE,
        help=f"Reject larger images (F103 default {F103_APP_MAX_SIZE}; F407VE use {F407VE_APP_MAX_SIZE})",
    )
    args = p.parse_args(argv)
    if not args.bin and not args.hex and not args.image:
        p.error("one of --bin / --hex / --image is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        bin_path = resolve_flash_bin(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    image = bin_path.read_bytes()
    if not image:
        print("error: empty bin", file=sys.stderr)
        return 2
    if len(image) > args.max_size:
        print(f"error: image {len(image)} > max {args.max_size}", file=sys.stderr)
        return 2

    sp = struct.unpack_from("<I", image, 0)[0]
    if (sp & 0xFFF00000) not in (0x20000000,):
        print(f"warning: vector SP=0x{sp:08X} unusual (expected 0x2000xxxx)")

    send_only = bool(args.send_only)
    gap_s = args.gap_ms / 1000.0
    use_window = not args.no_progress and not args.no_progress_window
    ui = None
    if use_window:
        ui = FlashProgressUI(bin_path.name, len(image))
        if not ui.start():
            print("warning: progress window failed to open")
            ui = None

    tr = CanTransport(
        args.interface,
        args.channel,
        args.bitrate,
        args.dry_run,
        verbose_tx=bool(args.verbose) or send_only or args.dry_run,
    )
    try:
        mode = "dry-run" if args.dry_run else ("send-only" if send_only else "normal")
        print(
            f"mode={mode} image={bin_path} size={len(image)} "
            f"crc=0x{crc32_mpeg2_like(image):08X}"
        )
        if ui is not None:
            ui.set_stage("握手 GET_INFO", pct=1.0)
        handshake(tr, args.timeout, send_only)
        if gap_s:
            time.sleep(gap_s)
        if not args.no_set_rtc:
            if ui is not None:
                ui.set_stage("同步 RTC", pct=2.0)
            set_rtc(tr, args.timeout, send_only)
            if gap_s:
                time.sleep(gap_s)
        if ui is not None:
            ui.set_stage("擦除 Flash", pct=4.0, detail="按扇区擦除，可能需要数秒")
        erase(tr, len(image), max(args.timeout, 5.0), send_only)
        if gap_s:
            time.sleep(gap_s)
        if ui is not None:
            ui.begin_write()
        write_image(
            tr,
            image,
            args.timeout,
            progress=not args.no_progress and ui is None,
            send_only=send_only,
            gap_s=gap_s,
            on_progress=None if ui is None else ui.set_write,
        )
        if gap_s:
            time.sleep(gap_s)
        if ui is not None:
            ui.set_stage("CRC 校验", pct=96.0)
        verify_crc(tr, image, args.timeout, send_only)
        if not args.no_jump:
            if gap_s:
                time.sleep(gap_s)
            if ui is not None:
                ui.set_stage("跳转 APP", pct=99.0)
            jump_app(tr, args.timeout, send_only)
        print("done")
        if ui is not None:
            ui.finish(True, "烧录完成")
        return 0
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        if ui is not None:
            ui.finish(False, str(exc))
        if not send_only and not args.dry_run:
            try:
                abort_session(tr, args.timeout)
            except Exception:
                pass
        return 1
    finally:
        tr.close()
        if ui is not None:
            ui.close()


if __name__ == "__main__":
    raise SystemExit(main())
