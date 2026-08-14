# STM32F407VE CAN2 Bootloader

Cube/Keil project for **STM32F407VET6** CAN IAP.

## Hardware

| Item | Value |
|------|--------|
| MCU | STM32F407VETx |
| IAP CAN | **CAN2** PB12(RX) / PB13(TX), 500 kbit/s |
| Vehicle CAN | CAN1 PA11/PA12（本 BL 不占用） |
| HSE | 8 MHz → SYSCLK 168 MHz（PLLM=4, PLLN=168） |

## Flash map

| Region | Address | Size |
|--------|---------|------|
| Bootloader | `0x08000000` | 16 KB (sector 0) |
| Application | `0x08004000` | up to 496 KB |

Scatter: `MDK-ARM/stm32f407ve_bl.sct`

## APP → BL

Magic `0xB00710AD` @ `0x2001BFF0` + `NVIC_SystemReset()`。  
头文件：`Bootloader/Inc/bl_enter_bl.h`

BL / APP 的 IRAM 都必须停在 `0x2001BFF0`（size `0x1BFF0`），把末 16 字节留给魔数。若 BL 仍按 `0x1C000` 链接，栈顶在 `0x2001C000`，上电初始化会先把魔数盖掉，再跳回 APP，主机就会一直握手失败。

## Build / flash

1. 用 Keil 打开 `MDK-ARM/Stm32F407_CAN2_Bootloader.uvprojx`，Rebuild
2. SWD 烧录 BL `.axf` / hex 到空片
3. 主机：

```bash
python tools/flash_can.py --bin app.bin --interface pcan --channel PCAN_USBBUS1 --max-size 507904 --no-progress
```

APP 必须链接在 `0x08004000`，并设置 `VECT_TAB_OFFSET=0x4000`（或等价）。
