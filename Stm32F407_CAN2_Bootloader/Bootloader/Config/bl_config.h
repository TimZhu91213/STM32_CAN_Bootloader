/**
 * @file bl_config.h
 * @brief F407VE CAN bootloader configuration
 */
#ifndef BL_CONFIG_H
#define BL_CONFIG_H

#define BL_TARGET_STM32F407VE
/* #define BL_TARGET_STM32F103C8 */
/* #define BL_TARGET_STM32F407VG */

#if defined(BL_TARGET_STM32F407VE)
  #include "targets/stm32f407ve.h"
#elif defined(BL_TARGET_STM32F103C8)
  #include "targets/stm32f103c8.h"
#elif defined(BL_TARGET_STM32F407VG)
  #include "targets/stm32f407vg.h"
#else
  #error "Define a BL_TARGET_* in bl_config.h"
#endif

#define BL_PROTOCOL_VERSION         1U
#define BL_FW_VERSION_MAJOR         0U
#define BL_FW_VERSION_MINOR         20U

#define BL_CAN_ID_CMD               0x700U
#define BL_CAN_ID_RSP               0x701U

#define BL_CAN_DATA_BYTES           6U
#define BL_CAN_TX_GAP_MS            1U
#define BL_BOOT_LISTEN_MS           0U

#ifndef BL_SHARED_MAGIC_ADDR
#define BL_SHARED_MAGIC_ADDR        BL_SHARED_MAGIC_ADDR_DEFAULT
#endif
#define BL_SHARED_MAGIC_VALUE       (0xB00710ADUL)

#define BL_HOST_RSP_TIMEOUT_MS      500U
#define BL_SESSION_IDLE_MS          10000U
#define BL_INFO_MAGIC               0x424C0001UL

#endif /* BL_CONFIG_H */
