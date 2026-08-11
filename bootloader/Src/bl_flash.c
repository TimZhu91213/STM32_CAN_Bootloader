/**
 * Flash port — F103 page erase / halfword program.
 * Critical ops run from RAM (.RamFunc) — programming Flash while fetching
 * from Flash can stall forever on F1.
 */
#include "bl_flash.h"

#if defined(BL_TARGET_STM32F103C8)
#include "stm32f1xx_hal.h"
#elif defined(BL_TARGET_STM32F407VG)
#include "stm32f4xx_hal.h"
#else
#error "Unsupported target for bl_flash.c"
#endif

#if defined(__ARMCC_VERSION) || defined(__GNUC__)
#define BL_RAMFUNC __attribute__((section(".RamFunc"), noinline))
#else
#define BL_RAMFUNC
#endif

#if defined(BL_TARGET_STM32F103C8)

static uint8_t s_pending_byte;
static uint8_t s_has_pending;
static uint32_t s_pending_addr;

BL_RAMFUNC static void flash_clear_flags_ram(void)
{
    FLASH->SR = (FLASH_SR_EOP | FLASH_SR_PGERR | FLASH_SR_WRPRTERR);
}

BL_RAMFUNC static int flash_wait_bsy_ram(uint32_t spins_max)
{
    uint32_t spins = 0u;
    while ((FLASH->SR & FLASH_SR_BSY) != 0u) {
        if (++spins > spins_max) {
            return 0;
        }
    }
    if ((FLASH->SR & (FLASH_SR_PGERR | FLASH_SR_WRPRTERR)) != 0u) {
        flash_clear_flags_ram();
        return 0;
    }
    return 1;
}

BL_RAMFUNC static int program_halfword_ram(uint32_t addr, uint16_t half)
{
    if ((addr & 1u) != 0u) {
        return 0;
    }
    if (!flash_wait_bsy_ram(500000u)) {
        return 0;
    }
    flash_clear_flags_ram();

    FLASH->CR |= FLASH_CR_PG;
    *(__IO uint16_t *)addr = half;
    if (!flash_wait_bsy_ram(500000u)) {
        FLASH->CR &= (uint32_t)(~FLASH_CR_PG);
        return 0;
    }
    FLASH->CR &= (uint32_t)(~FLASH_CR_PG);

    if (*(__IO uint16_t *)addr != half) {
        return 0;
    }
    return 1;
}

BL_RAMFUNC static int erase_page_ram(uint32_t page_addr)
{
    if (!flash_wait_bsy_ram(2000000u)) {
        return 0;
    }
    flash_clear_flags_ram();

    FLASH->CR |= FLASH_CR_PER;
    FLASH->AR = page_addr;
    FLASH->CR |= FLASH_CR_STRT;
    if (!flash_wait_bsy_ram(2000000u)) {
        FLASH->CR &= (uint32_t)(~FLASH_CR_PER);
        return 0;
    }
    FLASH->CR &= (uint32_t)(~FLASH_CR_PER);
    return 1;
}

#endif /* F103 */

bool bl_flash_addr_in_app(uint32_t abs_addr, uint32_t len)
{
    if (len == 0u) {
        return false;
    }
    if (abs_addr < BL_APP_START_ADDR) {
        return false;
    }
    if ((abs_addr + len) > (BL_APP_START_ADDR + BL_APP_MAX_SIZE)) {
        return false;
    }
    return true;
}

bool bl_flash_init(void)
{
#if defined(BL_TARGET_STM32F103C8)
    s_has_pending = 0u;
    s_pending_byte = 0xFFu;
    s_pending_addr = 0u;
    HAL_FLASH_Unlock();
#endif
    return true;
}

bool bl_flash_erase_app(uint32_t image_size)
{
    if (image_size == 0u || image_size > BL_APP_MAX_SIZE) {
        return false;
    }

#if defined(BL_TARGET_STM32F103C8)
    {
        uint32_t pages = (image_size + BL_FLASH_PAGE_SIZE - 1u) / BL_FLASH_PAGE_SIZE;
        uint32_t i;
        int ok = 1;

        s_has_pending = 0u;
        HAL_FLASH_Unlock();

        __disable_irq();
        for (i = 0u; i < pages; i++) {
            if (!erase_page_ram(BL_APP_START_ADDR + (i * BL_FLASH_PAGE_SIZE))) {
                ok = 0;
                break;
            }
        }
        __enable_irq();
        return ok != 0;
    }

#elif defined(BL_TARGET_STM32F407VG)
    (void)image_size;
    return false;
#endif
}

bool bl_flash_program(uint32_t abs_addr, const uint8_t *data, uint32_t len)
{
    if (!bl_flash_addr_in_app(abs_addr, len) || data == 0) {
        return false;
    }

#if defined(BL_TARGET_STM32F103C8)
    {
        uint32_t i = 0u;
        uint32_t wr = abs_addr;
        int ok = 1;

        HAL_FLASH_Unlock();
        __disable_irq();

        if (s_has_pending != 0u) {
            if (abs_addr != (s_pending_addr + 1u)) {
                ok = 0;
            } else {
                uint16_t half = (uint16_t)s_pending_byte | ((uint16_t)data[0] << 8);
                if (!program_halfword_ram(s_pending_addr, half)) {
                    ok = 0;
                } else {
                    s_has_pending = 0u;
                    i = 1u;
                    wr = abs_addr + 1u;
                }
            }
        }

        while (ok && (i < len)) {
            if ((i + 1u) < len) {
                uint16_t half = (uint16_t)data[i] | ((uint16_t)data[i + 1u] << 8);
                if (!program_halfword_ram(wr, half)) {
                    ok = 0;
                    break;
                }
                wr += 2u;
                i += 2u;
            } else {
                s_pending_byte = data[i];
                s_pending_addr = wr;
                s_has_pending = 1u;
                i += 1u;
            }
        }

        __enable_irq();
        return ok != 0;
    }

#elif defined(BL_TARGET_STM32F407VG)
    (void)abs_addr;
    (void)data;
    (void)len;
    return false;
#endif
}

bool bl_flash_flush_pending(void)
{
#if defined(BL_TARGET_STM32F103C8)
    int ok = 1;

    if (s_has_pending == 0u) {
        return true;
    }
    HAL_FLASH_Unlock();
    __disable_irq();
    {
        uint16_t half = (uint16_t)s_pending_byte | 0xFF00u;
        ok = program_halfword_ram(s_pending_addr, half);
    }
    __enable_irq();
    if (ok) {
        s_has_pending = 0u;
    }
    return ok != 0;
#else
    return true;
#endif
}

bool bl_flash_read(uint32_t abs_addr, uint8_t *data, uint32_t len)
{
    if (!bl_flash_addr_in_app(abs_addr, len) || data == 0) {
        return false;
    }
    {
        const uint8_t *src = (const uint8_t *)abs_addr;
        uint32_t i;
        for (i = 0; i < len; i++) {
            data[i] = src[i];
        }
    }
    return true;
}
