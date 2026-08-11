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
- Reserve SRAM `0x20004FF0..0x20004FFF` (IRAM size `0x4FF0`)
- Rebuild/flash bootloader **bl ≥ 0.16** so it honors the magic flag
