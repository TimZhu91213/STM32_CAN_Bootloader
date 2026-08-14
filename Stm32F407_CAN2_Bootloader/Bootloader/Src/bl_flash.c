/**
 * Flash port — STM32F407 sector erase / byte program.
 */
#include "bl_flash.h"
#include "stm32f4xx_hal.h"

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
    HAL_FLASH_Unlock();
    __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_EOP | FLASH_FLAG_OPERR | FLASH_FLAG_WRPERR |
                           FLASH_FLAG_PGAERR | FLASH_FLAG_PGPERR | FLASH_FLAG_PGSERR);
    return true;
}

/** Map absolute flash address to HAL sector index (F407 512KB / 1MB low sectors). */
static uint32_t flash_addr_to_sector(uint32_t addr)
{
    if (addr < 0x08004000UL) {
        return FLASH_SECTOR_0;
    }
    if (addr < 0x08008000UL) {
        return FLASH_SECTOR_1;
    }
    if (addr < 0x0800C000UL) {
        return FLASH_SECTOR_2;
    }
    if (addr < 0x08010000UL) {
        return FLASH_SECTOR_3;
    }
    if (addr < 0x08020000UL) {
        return FLASH_SECTOR_4;
    }
    if (addr < 0x08040000UL) {
        return FLASH_SECTOR_5;
    }
    if (addr < 0x08060000UL) {
        return FLASH_SECTOR_6;
    }
    if (addr < 0x08080000UL) {
        return FLASH_SECTOR_7;
    }
    /* F407VG 1MB continues with sector 8..11 — VE stops at 512KB */
    if (addr < 0x080A0000UL) {
        return FLASH_SECTOR_8;
    }
    if (addr < 0x080C0000UL) {
        return FLASH_SECTOR_9;
    }
    if (addr < 0x080E0000UL) {
        return FLASH_SECTOR_10;
    }
    return FLASH_SECTOR_11;
}

bool bl_flash_erase_app(uint32_t image_size)
{
    FLASH_EraseInitTypeDef erase = {0};
    uint32_t sector_error = 0;
    uint32_t first;
    uint32_t last;
    uint32_t end_addr;

    if (image_size == 0u || image_size > BL_APP_MAX_SIZE) {
        return false;
    }

    end_addr = BL_APP_START_ADDR + image_size - 1u;
    first = flash_addr_to_sector(BL_APP_START_ADDR);
    last = flash_addr_to_sector(end_addr);
    if (last < first) {
        return false;
    }

    HAL_FLASH_Unlock();
    __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_EOP | FLASH_FLAG_OPERR | FLASH_FLAG_WRPERR |
                           FLASH_FLAG_PGAERR | FLASH_FLAG_PGPERR | FLASH_FLAG_PGSERR);

    erase.TypeErase = FLASH_TYPEERASE_SECTORS;
    erase.VoltageRange = FLASH_VOLTAGE_RANGE_3;
    erase.Sector = first;
    erase.NbSectors = (last - first) + 1u;

    if (HAL_FLASHEx_Erase(&erase, &sector_error) != HAL_OK) {
        return false;
    }
    return true;
}

bool bl_flash_program(uint32_t abs_addr, const uint8_t *data, uint32_t len)
{
    uint32_t i;

    if (!bl_flash_addr_in_app(abs_addr, len) || data == 0) {
        return false;
    }

    HAL_FLASH_Unlock();
    for (i = 0; i < len; i++) {
        if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_BYTE, abs_addr + i, data[i]) != HAL_OK) {
            return false;
        }
    }
    return true;
}

bool bl_flash_flush_pending(void)
{
    /* F4 programs by byte — nothing buffered */
    return true;
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
