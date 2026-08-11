#ifndef BL_FLASH_H
#define BL_FLASH_H

#include <stdint.h>
#include <stdbool.h>
#include "bl_config.h"

#ifdef __cplusplus
extern "C" {
#endif

bool bl_flash_init(void);

/** Erase application region enough to hold image_size bytes (from APP start). */
bool bl_flash_erase_app(uint32_t image_size);

/** Program bytes at absolute flash address (must be inside APP region). */
bool bl_flash_program(uint32_t abs_addr, const uint8_t *data, uint32_t len);

/** Flush buffered odd byte (pad 0xFF). Call before CRC / JUMP. */
bool bl_flash_flush_pending(void);

/** Read back helper (optional verify). */
bool bl_flash_read(uint32_t abs_addr, uint8_t *data, uint32_t len);

bool bl_flash_addr_in_app(uint32_t abs_addr, uint32_t len);

#ifdef __cplusplus
}
#endif

#endif /* BL_FLASH_H */
