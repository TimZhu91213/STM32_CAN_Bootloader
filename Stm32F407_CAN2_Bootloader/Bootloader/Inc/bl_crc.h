#ifndef BL_CRC_H
#define BL_CRC_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** IEEE CRC-32 (same as Python binascii.crc32 / zlib). */
uint32_t bl_crc32(const uint8_t *data, uint32_t len);

/** CRC over application flash image_size bytes starting at BL_APP_START_ADDR. */
uint32_t bl_crc32_flash(uint32_t image_size);

#ifdef __cplusplus
}
#endif

#endif /* BL_CRC_H */
