/**
 * @file bl_enter_bl.h
 * @brief Call from application CAN RX path to re-enter bootloader.
 *
 * APP must:
 *  1) Keep a CAN filter that accepts ID 0x700 (BL_CAN_ID_CMD)
 *  2) In RX IRQ / callback, if cmd is GET_INFO/ERASE (or any 0x700), call
 *     bl_app_request_bootloader()
 *  3) Reserve last 16 bytes of SRAM (do not place .data/.bss there):
 *     IRAM size 0x4FF0 instead of 0x5000, or linker NOLOAD section at 0x20004FF0
 *
 * Soft reset keeps SRAM magic; BL clears it and stays in update mode.
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

/** Write magic and reset into bootloader (does not return). */
static inline void bl_app_request_bootloader(void)
{
    *(volatile uint32_t *)BL_SHARED_MAGIC_ADDR = BL_SHARED_MAGIC_VALUE;
    __DSB();
    __ISB();
    NVIC_SystemReset();
}

/**
 * Returns 1 if this CAN frame should force re-entry to BL.
 * Typical: standard ID 0x700, DLC>=1, cmd GET_INFO(0x01) or ERASE(0x02).
 */
static inline int bl_app_is_bootloader_cmd(uint32_t can_id, const uint8_t *data, uint8_t dlc)
{
    uint8_t cmd;
    if (can_id != BL_CAN_ID_CMD || data == 0 || dlc < 1u) {
        return 0;
    }
    cmd = data[0];
    /* Any BL command is enough; GET_INFO/ERASE are the usual first frames */
    if (cmd >= 0x01u && cmd <= 0x07u) {
        return 1;
    }
    return 0;
}

#ifdef __cplusplus
}
#endif

#endif /* BL_ENTER_BL_H */
