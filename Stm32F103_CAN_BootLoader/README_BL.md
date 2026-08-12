# Stm32F103_CAN_BootLoader — 集成说明

CubeMX 工程已接入 `can-bootloader` 协议层。

## 分区

| 区域 | 地址 | 大小 |
|------|------|------|
| Bootloader（本工程） | `0x08000000` | 16 KB（scatter: `MDK-ARM/stm32f103c8_bl.sct`） |
| Application | `0x08004000` | 48 KB |

## Keil

1. 打开 `MDK-ARM/Stm32F103_CAN_BootLoader.uvprojx`
2. 确认工程组 **Bootloader** 含 5 个 `.c`
3. Include 已含 `Bootloader/Inc|Config|Protocol`
4. Rebuild → Download

上电：若 APP 置了升级魔数 → 留在 BL；否则 **立即跳转 APP**。  
`JUMP_APP` **只应答、不软跳转**；烧录结束后停在 BL，**复位/下电** 后进 APP。  
运行中升级：APP 检测 `0x700` → `bl_app_request_bootloader()`。

### 运行中再进 Bootloader（APP 侧）

APP 用 CAN RX 中断检测 `0x700`，调用 `Bootloader/Inc/bl_enter_bl.h`：

```c
#include "bl_enter_bl.h"
/* in CAN RX IRQ / FIFO callback: */
if (bl_app_is_bootloader_cmd(id, data, dlc)) {
  bl_app_request_bootloader(); /* magic + SystemReset → BL stays */
}
```

APP 链接请把 IRAM 末 16 字节留给魔数（或 Size 用 `0x4FF0`）。

## PC 侧测试

先 `flash_can_send_only` 看能否收到设备 `0x701` 应答（需板子已运行本 BL）。

正常带应答烧录：

```text
--bin app.bin --interface pcan --channel PCAN_USBBUS1
```

（不要加 `--send-only` / `--dry-run`）

## CAN

- 引脚：PA11/PA12
- 500 kbit/s（与脚本默认一致）
- 命令 ID `0x700` / 应答 `0x701`
