/**
 * @file bl_config.h
 * @brief Single place to switch MCU target and CAN protocol parameters.
 *
 * Host script (tools/flash_can.py) mirrors these IDs in bl_protocol.py —
 * keep them in sync when you change anything.
 */
#ifndef BL_CONFIG_H
#define BL_CONFIG_H

/* ========== Select ONE target ========== */
#define BL_TARGET_STM32F103C8
/* #define BL_TARGET_STM32F407VG */

#if defined(BL_TARGET_STM32F103C8)
  #include "targets/stm32f103c8.h"
#elif defined(BL_TARGET_STM32F407VG)
  #include "targets/stm32f407vg.h"
#else
  #error "Define a BL_TARGET_* in bl_config.h"
#endif

/* ========== Protocol / version ========== */
#define BL_PROTOCOL_VERSION         1U
#define BL_FW_VERSION_MAJOR         0U
#define BL_FW_VERSION_MINOR         18U

/* ========== CAN identifiers (11-bit standard) ==========
 * Host -> device : BL_CAN_ID_CMD
 * Device -> host : BL_CAN_ID_RSP
 */
#define BL_CAN_ID_CMD               0x700U
#define BL_CAN_ID_RSP               0x701U

/* Image bytes per WRITE_DATA after the seq byte (frame: [0x04][seq][data…]) */
#define BL_CAN_DATA_BYTES           6U

/* Quiet time before/after each BL TX on 0x701 (ms) */
#define BL_CAN_TX_GAP_MS            1U

/* After reset: if APP set update magic → stay in BL; else jump APP immediately.
 * (Host upgrade while APP runs: APP detects 0x700 → magic + SystemReset.) */
#define BL_BOOT_LISTEN_MS           0U

/* Shared with APP (last 16B of 20KB SRAM). Soft-reset keeps it; power-on does not.
 * APP: bl_enter_bl.h → set magic + NVIC_SystemReset() when RX 0x700 BL cmd. */
#define BL_SHARED_MAGIC_ADDR        (0x20004FF0UL)
#define BL_SHARED_MAGIC_VALUE       (0xB00710ADUL)

/* Session timeouts (ms) */
#define BL_HOST_RSP_TIMEOUT_MS      500U
#define BL_SESSION_IDLE_MS          10000U

/* Magic in GET_INFO response so host can reject wrong devices */
#define BL_INFO_MAGIC               0x424C0001UL

#endif /* BL_CONFIG_H */
