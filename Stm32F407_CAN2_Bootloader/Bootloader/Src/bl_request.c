#include "bl_request.h"
#include "bl_config.h"

#include <stdint.h>

bool bl_request_consume_update_flag(void)
{
    volatile uint32_t *p = (volatile uint32_t *)BL_SHARED_MAGIC_ADDR;
    if (*p == BL_SHARED_MAGIC_VALUE) {
        *p = 0u;
        return true;
    }
    return false;
}
