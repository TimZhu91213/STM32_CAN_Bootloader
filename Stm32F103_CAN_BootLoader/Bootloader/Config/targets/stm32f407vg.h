/**
 * @file stm32f407vg.h
 * @brief Target parameters stub for STM32F407VGT6 (1MB Flash)
 *
 * Enable with BL_TARGET_STM32F407VG. Flash erase uses SECTORS, not pages —
 * implement bl_flash_* with HAL sector erase when you port.
 */
#ifndef BL_TARGET_STM32F407VG_H
#define BL_TARGET_STM32F407VG_H

#define BL_TARGET_NAME              "STM32F407VG"

#define BL_FLASH_BASE               0x08000000UL
#define BL_FLASH_SIZE               (1024UL * 1024UL)

/* F407 sector sizes vary; treat erase unit as smallest sector for sizing math */
#define BL_FLASH_PAGE_SIZE          (16UL * 1024UL)

/* Example: BL in sector 0 (16KB), app from sector 1 */
#define BL_BOOTLOADER_SIZE          (16UL * 1024UL)
#define BL_APP_START_ADDR           (BL_FLASH_BASE + BL_BOOTLOADER_SIZE)
#define BL_APP_MAX_SIZE             (BL_FLASH_SIZE - BL_BOOTLOADER_SIZE)

#define BL_HAS_VTOR                 1
#define BL_NEEDS_SRAM_VECTOR_REMAP  0

#define BL_CAN_INSTANCE             1
#define BL_CAN_BAUDRATE             500000UL

#define BL_MCU_ID_CODE              0x00000413UL

#endif /* BL_TARGET_STM32F407VG_H */
