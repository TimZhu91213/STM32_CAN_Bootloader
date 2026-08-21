#!/usr/bin/env python3
"""PCAN Bus helper for GUI / tools."""

from __future__ import annotations

PCAN_INTERFACE = "pcan"
PCAN_CHANNELS = ["PCAN_USBBUS1", "PCAN_USBBUS2", "PCAN_USBBUS3", "PCAN_USBBUS4"]


def open_can_bus(*, interface: str, channel: str, bitrate: int, app_name: str | None = None):
    """Open a python-can Bus. GUI uses PCAN only; CLI may pass other interfaces."""
    import can  # type: ignore

    return can.Bus(
        interface=interface.strip().lower(),
        channel=channel.strip(),
        bitrate=bitrate,
    )
