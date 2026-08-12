#!/usr/bin/env python3
"""
CAN bootloader host flasher (F103 first; params portable).

Flow (mirrors DieBieMS erase -> write chunks -> jump):
  1) GET_INFO handshake
  2) ERASE(image_size)
  3) SET_ADDR(0) + WRITE_DATA stream
  4) CRC(image)
  5) JUMP_APP

Examples:
  python flash_can.py --bin app.bin --interface pcan --channel PCAN_USBBUS1
  python flash_can.py --bin _test_app.bin --send-only
  python flash_can.py --bin app.bin --dry-run
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

from bl_protocol import (
    BL_CAN_ID_CMD,
    BL_CAN_ID_RSP,
    BL_CMD_ABORT,
    BL_CMD_CRC,
    BL_CMD_ERASE,
    BL_CMD_GET_INFO,
    BL_CMD_JUMP_APP,
    BL_CMD_SET_ADDR,
    BL_CMD_WRITE_DATA,
    BL_PROTOCOL_VERSION,
    BL_STATUS_OK,
    CHUNK_DATA_BYTES,
    F103_APP_MAX_SIZE,
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
        if (offset == len(chunk)) or (offset % 64 == 0) or (offset >= total):
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CAN bootloader flasher")
    p.add_argument("--bin", required=True, type=Path, help="Application .bin (linked at APP start)")
    p.add_argument("--interface", default="pcan", help="python-can interface (pcan/candlelight/socketcan/...)")
    p.add_argument("--channel", default="PCAN_USBBUS1", help="CAN channel (PCAN: PCAN_USBBUS1)")
    p.add_argument("--bitrate", type=int, default=500000, help="CAN bitrate")
    p.add_argument("--gap-ms", type=float, default=2.0, help="Delay between frames (ms)")
    p.add_argument("--timeout", type=float, default=3.0, help="Per-frame response timeout (s)")
    p.add_argument("--dry-run", action="store_true", help="Do not open CAN; simulate OK replies")
    p.add_argument(
        "--send-only",
        action="store_true",
        help="Open PCAN and send all frames; do not wait for device replies",
    )
    p.add_argument("--verbose", action="store_true", help="Print every TX/RX frame")
    p.add_argument("--no-jump", action="store_true", help="Skip JUMP_APP")
    p.add_argument("--no-progress", action="store_true", help="Disable tqdm")
    p.add_argument("--max-size", type=int, default=F103_APP_MAX_SIZE, help="Reject larger images")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    image = args.bin.read_bytes()
    if not image:
        print("error: empty bin", file=sys.stderr)
        return 2
    if len(image) > args.max_size:
        print(f"error: image {len(image)} > max {args.max_size}", file=sys.stderr)
        return 2

    sp = struct.unpack_from("<I", image, 0)[0]
    if (sp & 0xFFF00000) not in (0x20000000,):
        print(f"warning: vector SP=0x{sp:08X} unusual for F103 (expected 0x2000xxxx)")

    send_only = bool(args.send_only)
    gap_s = args.gap_ms / 1000.0

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
            f"mode={mode} image={args.bin} size={len(image)} "
            f"crc=0x{crc32_mpeg2_like(image):08X}"
        )
        handshake(tr, args.timeout, send_only)
        if gap_s:
            time.sleep(gap_s)
        erase(tr, len(image), max(args.timeout, 5.0), send_only)
        if gap_s:
            time.sleep(gap_s)
        write_image(
            tr,
            image,
            args.timeout,
            progress=not args.no_progress,
            send_only=send_only,
            gap_s=gap_s,
        )
        if gap_s:
            time.sleep(gap_s)
        verify_crc(tr, image, args.timeout, send_only)
        if not args.no_jump:
            if gap_s:
                time.sleep(gap_s)
            jump_app(tr, args.timeout, send_only)
        print("done")
        return 0
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        if not send_only and not args.dry_run:
            try:
                abort_session(tr, args.timeout)
            except Exception:
                pass
        return 1
    finally:
        tr.close()


if __name__ == "__main__":
    raise SystemExit(main())
