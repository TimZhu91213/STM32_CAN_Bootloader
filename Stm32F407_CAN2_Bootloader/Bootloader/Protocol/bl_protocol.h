/**
 * @file bl_protocol.h
 * @brief CAN bootloader command set (shared with host conceptually).
 *
 * Frame layout (classic CAN, DLC = 1..8):
 *   byte0 : command (bl_cmd_t)
 *   byte1..7 : command-specific payload
 *
 * Inspired by DieBieMS/VESC COMM_ERASE_NEW_APP / WRITE_NEW_APP_DATA / JUMP,
 * simplified for 8-byte CAN frames (sequential write stream).
 */
#ifndef BL_PROTOCOL_H
#define BL_PROTOCOL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    BL_CMD_GET_INFO     = 0x01, /* host->dev; rsp carries device info          */
    BL_CMD_ERASE        = 0x02, /* payload: image_size u32 LE                  */
    BL_CMD_SET_ADDR     = 0x03, /* payload: offset u32 LE (relative to APP)    */
    BL_CMD_WRITE_DATA   = 0x04, /* payload: [seq][up to 6 image bytes]        */
    BL_CMD_CRC          = 0x05, /* payload: crc32 u32 LE over whole image      */
    BL_CMD_JUMP_APP     = 0x06, /* jump to application                        */
    BL_CMD_ABORT        = 0x07, /* abort session                              */
    BL_CMD_SET_RTC      = 0x08, /* payload: unix_ts u32 LE (PC local time)    */
} bl_cmd_t;

typedef enum {
    BL_STATUS_OK            = 0x00,
    BL_STATUS_BUSY          = 0x01,
    BL_STATUS_ERR_PARAM     = 0x02,
    BL_STATUS_ERR_FLASH     = 0x03,
    BL_STATUS_ERR_CRC       = 0x04,
    BL_STATUS_ERR_STATE     = 0x05,
    BL_STATUS_ERR_UNKNOWN   = 0xFF,
} bl_status_t;

/*
 * GET_INFO response (multi-frame friendly; first rsp frame):
 *   [0]=BL_CMD_GET_INFO
 *   [1]=BL_STATUS_OK
 *   [2]=protocol_version
 *   [3]=bl_major
 *   [4]=bl_minor
 *   [5..7]=reserved / part of magic
 *
 * Host then may request extended info via repeated GET_INFO or we pack
 * APP start in a second response — see bl_can.c / flash_can.py.
 */

#ifdef __cplusplus
}
#endif

#endif /* BL_PROTOCOL_H */
