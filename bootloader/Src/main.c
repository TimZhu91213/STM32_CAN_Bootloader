/**
 * Bootloader entry (HAL-agnostic skeleton).
 *
 * Next step: generate CubeMX project for F103C8 (CAN1 + HSE), then:
 *   - keep this main loop
 *   - implement bl_can_hw_* using HAL_CAN
 *   - call SystemClock_Config / MX_CAN_Init from Cube
 */
#include "bl_config.h"
#include "bl_flash.h"
#include "bl_can.h"
#include "bl_app_jump.h"

/* Optional: hold a GPIO at reset to force stay-in-bootloader */
static bool bl_force_stay(void)
{
    return false;
}

int main(void)
{
    /* HAL_Init(); SystemClock_Config(); MX_GPIO_Init(); MX_CAN_Init(); */

    (void)bl_flash_init();
    (void)bl_can_init();

    /* Auto-jump to app if valid and not forced into BL */
    if (!bl_force_stay() && bl_app_is_valid()) {
        /* Small delay window could be added for host to abort-jump via CAN */
        bl_app_jump();
    }

    for (;;) {
        bl_can_poll();
    }
}
