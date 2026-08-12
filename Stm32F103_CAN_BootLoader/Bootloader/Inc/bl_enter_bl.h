/**
 * @file bl_enter_bl.h
 * @brief Copy this header into the application project (or add include path).
 * @see can-bootloader/app_hooks/bl_enter_bl.h
 */
#ifndef BL_ENTER_BL_H
#define BL_ENTER_BL_H

#include <stdint.h>
#include "stm32f1xx.h"

#ifndef BL_SHARED_MAGIC_ADDR
#define BL_SHARED_MAGIC_ADDR   (0x20004FF0UL)
#endif
#ifndef BL_SHARED_MAGIC_VALUE
#define BL_SHARED_MAGIC_VALUE  (0xB00710ADUL)
#endif
#ifndef BL_CAN_ID_CMD
#define BL_CAN_ID_CMD          (0x700U)
#endif

#ifdef __cplusplus
extern "C" {
#endif

static inline void bl_app_request_bootloader(void)
{
    *(volatile uint32_t *)BL_SHARED_MAGIC_ADDR = BL_SHARED_MAGIC_VALUE;
    __DSB();
    __ISB();
    NVIC_SystemReset();
}

static inline int bl_app_is_bootloader_cmd(uint32_t can_id, const uint8_t *data, uint8_t dlc)
{
    uint8_t cmd;
    if (can_id != BL_CAN_ID_CMD || data == 0 || dlc < 1u) {
        return 0;
    }
    cmd = data[0];
    if (cmd >= 0x01u && cmd <= 0x07u) {
        return 1;
    }
    return 0;
}

#ifdef __cplusplus
}
#endif

#endif /* BL_ENTER_BL_H */
