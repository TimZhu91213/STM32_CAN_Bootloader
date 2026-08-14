# APP → Bootloader re-entry

While the application is running, the bootloader is not polling CAN.
Detect upgrade commands in the **APP CAN RX interrupt**, then soft-reset into BL.

## Hook

```c
#include "bl_enter_bl.h"

void APP_CAN_RxCallback(uint32_t id, const uint8_t *data, uint8_t dlc)
{
    if (bl_app_is_bootloader_cmd(id, data, dlc)) {
        bl_app_request_bootloader(); /* does not return */
    }
    /* ... normal APP CAN handling ... */
}
```

Requirements:
- CAN filter accepts standard ID `0x700`
- Reserve SRAM magic location (do not place `.data`/`.bss` there):
  - F103: `0x20004FF0` (IRAM size `0x4FF0`) — use `app_hooks/bl_enter_bl.h`
  - F407VE: `0x2001BFF0` — use `Stm32F407_CAN2_Bootloader/Bootloader/Inc/bl_enter_bl.h`
- Rebuild/flash matching bootloader so it honors the magic flag
