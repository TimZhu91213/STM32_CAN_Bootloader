# CAN Bootloader (STM32F103 + STM32F407VE)

参考 DieBieMS 的「擦除 → 分包写入 → 跳转」思路，做成 **CAN 版 IAP**。  
芯片相关参数集中在 `config/`，Cube 工程在 `Stm32F103_CAN_BootLoader/` / `Stm32F407_CAN2_Bootloader/`。

## 目录

```
config/           目标芯片参数 + CAN ID（改这里即可换芯片）
protocol/         命令定义（C 头 + 文档）
bootloader/       BL 源码骨架（可移植参考）
tools/            Python 烧录脚本（主站）
Stm32F103_CAN_BootLoader/     F103 可烧录 Cube/Keil 工程
Stm32F407_CAN2_Bootloader/    F407VE CAN2 IAP Cube/Keil 工程
```

## Flash 分区

### F103C8（64KB）

| 区域 | 地址 | 大小 |
|------|------|------|
| Bootloader | `0x08000000` | 16 KB |
| Application | `0x08004000` | 48 KB |

### F407VE（512KB）

| 区域 | 地址 | 大小 |
|------|------|------|
| Bootloader（sector 0） | `0x08000000` | 16 KB |
| Application（sector 1…） | `0x08004000` | 496 KB |

F407 擦除按 **扇区**（非 F1 页擦）。IAP 走 **CAN2 PB12/PB13**，500 kbit/s。

跳转 APP：`SCB->VTOR = APP基址`。`JUMP_APP` 应答后软跳转。

APP→BL：SRAM magic `0xB00710AD`（F103 `@0x20004FF0`，F407 `@0x2001BFF0`）+ `NVIC_SystemReset()`。

## 可改参数（移植入口）

| 文件 | 改什么 |
|------|--------|
| `config/bl_config.h` / 工程内 `Bootloader/Config/bl_config.h` | 选目标宏、`BL_CAN_ID_*` |
| `config/targets/*.h` | Flash / APP 起点 / magic 地址 |
| `tools/bl_protocol.py` | 与 C 头同步的 CAN ID / 命令号 / `--max-size` 常量 |
| 工程内 `bl_flash.c` / `bl_can_hw_*.c` | 扇区擦写、CAN 硬件 |

## 主机脚本

```bash
cd tools
pip install -r requirements.txt
# F103
python flash_can.py --bin app.bin --interface pcan --channel PCAN_USBBUS1 --no-progress
# F407VE：可直接给 Keil 的 .hex（自动调用 Hex2bin-2.5 → .bin）
python flash_can.py --image F407_VET6_Test --interface pcan --channel PCAN_USBBUS1 --max-size 507904 --no-progress
python flash_can.py --hex ../F407_VET6_Test.hex --max-size 507904 --no-progress
```

流程：`GET_INFO → ERASE → SET_ADDR/WRITE_DATA → CRC → JUMP_APP`

## F407 工程要点

1. Keil 打开 `Stm32F407_CAN2_Bootloader/MDK-ARM/Stm32F407_CAN2_Bootloader.uvprojx`
2. Scatter：`stm32f407ve_bl.sct`（IROM 16KB @ `0x08000000`）
3. 空片：先 SWD 烧 BL，再 CAN 烧 APP（APP 必须 link 在 `0x08004000`）
4. 勿把 BL `.bin` 当 APP 烧

## 与 DieBieMS 的对应

| DieBieMS | 本工程 |
|----------|--------|
| UART VESC Packet | CAN 8 字节帧 |
| `COMM_ERASE_NEW_APP` | `BL_CMD_ERASE` |
| `COMM_WRITE_NEW_APP_DATA` | `SET_ADDR` + `WRITE_DATA` |
| 暂存区 + 独立 BL 仓 | BL 在 Flash 头，直写 APP 区 |
| DieBieMS-Tool | `tools/flash_can.py` |

## Hex2Bin

Keil 等 IDE 常输出 hex/mot；主机脚本认 `.bin`。可用 `Hex2bin` 转换后再烧录。

## ChangeLog
### V1.0.0 | 2026_08_14
- 在脚本中添加了自动化将hex转bin的操作
- 移植到F407VET6并经过测试，可以烧录并且自动跳转到app开始运行

### V1.0.1 | 2026_08_14
- 添加了烧录进度ui，已经过测试不会影响正常烧录动作