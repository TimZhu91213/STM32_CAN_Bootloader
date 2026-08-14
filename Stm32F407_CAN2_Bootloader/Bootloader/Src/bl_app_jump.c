#include "bl_app_jump.h"
#include "bl_config.h"
#include "stm32f4xx_hal.h"

typedef void (*pFunction)(void);

bool bl_app_is_valid(void)
{
    uint32_t sp = *(volatile uint32_t *)BL_APP_START_ADDR;
    uint32_t rv = *(volatile uint32_t *)(BL_APP_START_ADDR + 4u);

    if ((sp & 0xFFF00000u) != 0x20000000u) {
        return false;
    }
    if ((rv & 0xFF000000u) != 0x08000000u) {
        return false;
    }
    if ((rv & 1u) == 0u) {
        return false;
    }
    if (rv < BL_APP_START_ADDR || rv >= (BL_APP_START_ADDR + BL_APP_MAX_SIZE)) {
        return false;
    }
    return true;
}

void bl_app_jump(void)
{
    uint32_t app_sp;
    uint32_t app_reset;
    pFunction app_entry;
    uint32_t i;

    if (!bl_app_is_valid()) {
        return;
    }

    app_sp = *(volatile uint32_t *)BL_APP_START_ADDR;
    app_reset = *(volatile uint32_t *)(BL_APP_START_ADDR + 4u);
    app_entry = (pFunction)app_reset;

    HAL_SuspendTick();
    SysTick->CTRL = 0u;
    SysTick->LOAD = 0u;
    SysTick->VAL = 0u;

    __disable_irq();
    for (i = 0; i < 8u; i++) {
        NVIC->ICER[i] = 0xFFFFFFFFu;
        NVIC->ICPR[i] = 0xFFFFFFFFu;
    }

    SCB->VTOR = BL_APP_START_ADDR;
    __DSB();
    __ISB();
    __set_MSP(app_sp);
    app_entry();
}
