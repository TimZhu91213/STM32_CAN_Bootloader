#include "bl_crc.h"
#include "bl_config.h"

uint32_t bl_crc32(const uint8_t *data, uint32_t len)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint8_t b = 0; b < 8; b++) {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

uint32_t bl_crc32_flash(uint32_t image_size)
{
    const uint8_t *p = (const uint8_t *)BL_APP_START_ADDR;
    return bl_crc32(p, image_size);
}
