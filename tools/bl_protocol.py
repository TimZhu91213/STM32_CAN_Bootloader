"""
CAN bootloader protocol constants — keep in sync with:
  config/bl_config.h
  protocol/bl_protocol.h
  config/targets/stm32f103c8.h  (defaults for host-side checks)
"""

from __future__ import annotations

# CAN IDs (must match bl_config.h)
BL_CAN_ID_CMD = 0x700
BL_CAN_ID_RSP = 0x701

BL_PROTOCOL_VERSION = 1
BL_INFO_MAGIC = 0x424C0001

# Commands
BL_CMD_GET_INFO = 0x01
BL_CMD_ERASE = 0x02
BL_CMD_SET_ADDR = 0x03
BL_CMD_WRITE_DATA = 0x04
BL_CMD_CRC = 0x05
BL_CMD_JUMP_APP = 0x06
BL_CMD_ABORT = 0x07

# Status
BL_STATUS_OK = 0x00
BL_STATUS_BUSY = 0x01
BL_STATUS_ERR_PARAM = 0x02
BL_STATUS_ERR_FLASH = 0x03
BL_STATUS_ERR_CRC = 0x04
BL_STATUS_ERR_STATE = 0x05
BL_STATUS_ERR_UNKNOWN = 0xFF

STATUS_NAME = {
    BL_STATUS_OK: "OK",
    BL_STATUS_BUSY: "BUSY",
    BL_STATUS_ERR_PARAM: "ERR_PARAM",
    BL_STATUS_ERR_FLASH: "ERR_FLASH",
    BL_STATUS_ERR_CRC: "ERR_CRC",
    BL_STATUS_ERR_STATE: "ERR_STATE",
    BL_STATUS_ERR_UNKNOWN: "ERR_UNKNOWN",
}

# Default F103 layout (host validates against GET_INFO)
F103_APP_START = 0x08004000
F103_APP_MAX_SIZE = 48 * 1024
F103_PAGE_SIZE = 1024

# F407VE: BL sector0 16KB, APP from 0x08004000, 496KB max
F407VE_APP_START = 0x08004000
F407VE_APP_MAX_SIZE = 496 * 1024
F407VE_SECTOR_SIZE = 16 * 1024

CHUNK_DATA_BYTES = 6  # image bytes per WRITE (plus 1 seq byte in frame)


def u32_le(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=False)


def crc32_mpeg2_like(data: bytes) -> int:
    """
    Simple CRC32 (binascii) — firmware must use the same polynomial/init.
    Host and MCU both use zlib/binascii-compatible CRC-32 (IEEE).
    """
    import binascii

    return binascii.crc32(data) & 0xFFFFFFFF
