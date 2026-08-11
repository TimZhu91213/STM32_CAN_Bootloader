#!/usr/bin/env python3
"""
python-can 冒烟测试：检查 CAN 卡能否被打开、发送、接收。

用法示例：
  py -3 can_smoke_test.py --list
  py -3 can_smoke_test.py --interface pcan --channel PCAN_USBBUS1
  py -3 can_smoke_test.py --interface pcan --channel PCAN_USBBUS1 --listen 10
  py -3 can_smoke_test.py --interface candlelight --channel 0
"""

from __future__ import annotations

import argparse
import sys
import time


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def ensure_python_can():
    try:
        import can  # noqa: F401
    except ImportError:
        die(
            "未安装 python-can。请先执行:\n"
            "  py -3 -m pip install python-can"
        )
    import can

    return can


def cmd_list(can) -> int:
    print(f"python-can version: {can.__version__}")
    print("detect_available_configs():")
    try:
        configs = can.detect_available_configs()
    except Exception as exc:
        print(f"  (detect failed: {exc})")
        configs = []

    if not configs:
        print("  (empty)  — 可能驱动未装，或该卡不支持自动枚举")
        print("常见手动参数:")
        print("  candlelight / CANable : --interface candlelight --channel 0")
        print("  PCAN                  : --interface pcan --channel PCAN_USBBUS1")
        print("  socketcan (Linux)     : --interface socketcan --channel can0")
        return 0

    for i, cfg in enumerate(configs):
        print(f"  [{i}] {cfg}")
    return 0


def parse_data_hex(text: str) -> bytes:
    text = text.strip().replace(" ", "").replace("0x", "").replace("0X", "")
    if len(text) % 2:
        die("--send-data hex 长度必须是偶数")
    data = bytes.fromhex(text)
    if len(data) > 8:
        die("CAN 数据最多 8 字节")
    return data


def open_bus(can, interface: str, channel: str, bitrate: int):
    # channel: candlelight 常用 int；socketcan/pcan 常用 str
    ch: str | int = channel
    if interface in ("candlelight", "gs_usb", "kvaser", "ixxat") and channel.isdigit():
        ch = int(channel)

    print(f"Opening Bus(interface={interface!r}, channel={ch!r}, bitrate={bitrate}) ...")
    try:
        bus = can.Bus(interface=interface, channel=ch, bitrate=bitrate)
    except Exception as exc:
        die(
            f"打开失败: {exc}\n"
            "请检查: 驱动 / interface / channel / 是否被其他软件占用"
        )
    print(f"OK opened: {bus}")
    return bus


def cmd_test(can, args: argparse.Namespace) -> int:
    bus = open_bus(can, args.interface, str(args.channel), args.bitrate)
    try:
        # ---- send ----
        if not args.no_send:
            data = parse_data_hex(args.send_data)
            msg = can.Message(
                arbitration_id=args.send_id,
                data=data,
                is_extended_id=args.extended,
            )
            try:
                bus.send(msg)
                print(
                    f"OK sent id=0x{args.send_id:X} "
                    f"{'EXT' if args.extended else 'STD'} data={data.hex()}"
                )
            except Exception as exc:
                print(f"SEND failed: {exc}")
                print("提示: 无第二节点/无终端电阻时，有的卡会报错或进 Error Passive")

        # ---- listen / single recv ----
        listen_s = args.listen
        if listen_s > 0:
            print(f"Listening {listen_s:.1f}s for any frames ...")
            t_end = time.time() + listen_s
            count = 0
            while time.time() < t_end:
                rx = bus.recv(timeout=0.1)
                if rx is None:
                    continue
                count += 1
                print(
                    f"  RX id=0x{rx.arbitration_id:X} dlc={rx.dlc} "
                    f"data={bytes(rx.data).hex()} ts={getattr(rx, 'timestamp', 0):.3f}"
                )
            print(f"Done. received {count} frame(s)")
            if count == 0:
                print(
                    "未收到帧不一定是坏卡：\n"
                    "  - 只有一张卡、总线上没别的节点时，recv 经常为空\n"
                    "  - 只要前面 Opened + Sent 成功，卡基本可用\n"
                    "  - 接上 STM32 或第二台 CAN 设备后再听"
                )
        elif not args.no_send:
            print("单次等待回显 1s ...")
            rx = bus.recv(1.0)
            print(f"recv: {rx}")
            if rx is None:
                print("(无回帧：在单卡环境下通常正常)")

        print("PASS: CAN adapter open path works")
        return 0
    finally:
        bus.shutdown()
        print("bus closed")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="python-can CAN 卡冒烟测试")
    p.add_argument("--list", action="store_true", help="只枚举可用配置")
    p.add_argument("--interface", default="pcan", help="默认 pcan（PEAK）")
    p.add_argument("--channel", default="PCAN_USBBUS1", help="默认 PCAN_USBBUS1")
    p.add_argument("--bitrate", type=int, default=500000, help="默认 500000")
    p.add_argument("--send-id", type=lambda x: int(x, 0), default=0x123, help="发送 ID，默认 0x123")
    p.add_argument("--send-data", default="01020304", help="发送数据 hex，默认 01020304")
    p.add_argument("--extended", action="store_true", help="使用扩展帧")
    p.add_argument("--no-send", action="store_true", help="只打开/监听，不发送")
    p.add_argument("--listen", type=float, default=0.0, help="持续监听秒数，如 10")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    can = ensure_python_can()

    print("=== CAN smoke test ===")
    print(f"Python: {sys.version.split()[0]}")
    print(f"python-can: {can.__version__}")

    if args.list:
        return cmd_list(can)

    # 测试前也打印一次枚举，方便对照
    cmd_list(can)
    print("---")
    return cmd_test(can, args)


if __name__ == "__main__":
    raise SystemExit(main())
