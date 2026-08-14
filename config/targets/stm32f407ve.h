/**
 * @file stm32f407ve.h
 * @brief Target parameters for STM32F407VET6 (512KB Flash, 192KB RAM)
 */
#ifndef BL_TARGET_STM32F407VE_H
#define BL_TARGET_STM32F407VE_H

#define BL_TARGET_NAME              "STM32F407VE"

#define BL_FLASH_BASE               0x08000000UL
#define BL_FLASH_SIZE               (512UL * 1024UL)

/* F407 sector 0 = 16KB — used as erase-unit hint for host sizing */
#define BL_FLASH_PAGE_SIZE          (16UL * 1024UL)

/* Bootloader in sector 0; application from sector 1 */
#define BL_BOOTLOADER_SIZE          (16UL * 1024UL)
#define BL_APP_START_ADDR           (BL_FLASH_BASE + BL_BOOTLOADER_SIZE)
#define BL_APP_MAX_SIZE             (BL_FLASH_SIZE - BL_BOOTLOADER_SIZE)

#define BL_HAS_VTOR                 1
#define BL_NEEDS_SRAM_VECTOR_REMAP  0

/* IAP on CAN2 (PB12/PB13) — vehicle CAN1 left alone */
#define BL_CAN_INSTANCE             2
#define BL_CAN_BAUDRATE             500000UL

#define BL_MCU_ID_CODE              0x00000413UL

/* Soft-reset magic at end of main SRAM (0x20000000..0x2001BFFF) */
#define BL_SHARED_MAGIC_ADDR_DEFAULT (0x2001BFF0UL)

#endif /* BL_TARGET_STM32F407VE_H */
