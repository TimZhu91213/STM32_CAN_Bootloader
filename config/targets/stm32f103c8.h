/**
 * @file stm32f103c8.h
 * @brief Target parameters for STM32F103C8T6 (64KB Flash, 20KB RAM)
 *
 * Switch target by defining BL_TARGET_STM32F103C8 in bl_config.h
 */
#ifndef BL_TARGET_STM32F103C8_H
#define BL_TARGET_STM32F103C8_H

#define BL_TARGET_NAME              "STM32F103C8"

/* ---- Flash geometry (medium-density F103: 1KB pages) ---- */
#define BL_FLASH_BASE               0x08000000UL
#define BL_FLASH_SIZE               (64UL * 1024UL)
#define BL_FLASH_PAGE_SIZE          1024UL

/* Bootloader occupies first 16KB -> leaves 48KB for application */
#define BL_BOOTLOADER_SIZE          (16UL * 1024UL)
#define BL_APP_START_ADDR           (BL_FLASH_BASE + BL_BOOTLOADER_SIZE)
#define BL_APP_MAX_SIZE             (BL_FLASH_SIZE - BL_BOOTLOADER_SIZE)

/* F103 (Cortex-M3) has SCB->VTOR — use it; SRAM remap fights APP .data at 0x20000000 */
#define BL_HAS_VTOR                 1
#define BL_NEEDS_SRAM_VECTOR_REMAP  0

/* ---- CAN peripheral defaults (override in board file if needed) ---- */
#define BL_CAN_INSTANCE             1          /* CAN1 */
#define BL_CAN_BAUDRATE             500000UL

/* ---- Clock (informational for host GET_INFO) ---- */
#define BL_MCU_ID_CODE              0x00000410UL  /* F1 family marker for script */

#endif /* BL_TARGET_STM32F103C8_H */
