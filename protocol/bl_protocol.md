# CAN Bootloader Protocol v1

Classic CAN (11-bit), 500 kbit/s default.

| Direction | ID | Name |
|-----------|-----|------|
| Host → BL | `0x700` | `BL_CAN_ID_CMD` |
| BL → Host | `0x701` | `BL_CAN_ID_RSP` |

## Frame

| Byte | Meaning |
|------|---------|
| 0 | `bl_cmd_t` |
| 1..7 | payload |

Response:

| Byte | Meaning |
|------|---------|
| 0 | echo cmd |
| 1 | `bl_status_t` |
| 2..7 | optional data |

## Upgrade sequence

1. `GET_INFO` — handshake  
2. `ERASE` + `image_size` (u32 LE)  
3. `SET_ADDR` + `offset=0` (u32 LE)  
4. many `WRITE_DATA`: `[seq][≤6 image bytes]`; ACK echoes `seq` in byte 2  

5. `CRC` + CRC32 (IEEE, same as Python `binascii.crc32`)  
6. `JUMP_APP`

Inspired by DieBieMS `COMM_ERASE_NEW_APP` / `COMM_WRITE_NEW_APP_DATA` / jump-to-bootloader, flattened for 8-byte CAN.
