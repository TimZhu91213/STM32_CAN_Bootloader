# CAN Bootloader (STM32F103 first)

参考 DieBieMS 的「擦除 → 分包写入 → 跳转」思路，做成 **CAN 版 IAP**。  
芯片相关参数集中在 `config/`，方便后续迁到 F407。

## 目录

```
config/           目标芯片参数 + CAN ID（改这里即可换芯片）
protocol/         命令定义（C 头 + 文档）
bootloader/       BL 源码骨架 + 链接脚本
tools/            Python 烧录脚本（主站）
```

## Flash 分区（F103C8 64KB）

| 区域 | 地址 | 大小 |
|------|------|------|
| Bootloader | `0x08000000` | 16 KB |
| Application | `0x08004000` | 48 KB |

换 F407：改 `config/targets/stm32f407vg.h`，并在 `bl_flash.c` 实现扇区擦除。

跳转 APP：使用 `SCB->VTOR = APP基址`（不再做 SRAM 向量 remap）。
`JUMP_APP` 应答后直接软跳转进入应用。

## 可改参数（移植入口）

| 文件 | 改什么 |
|------|--------|
| `config/bl_config.h` | 选目标宏、`BL_CAN_ID_*`、波特率相关超时 |
| `config/targets/*.h` | Flash 基址/大小/页大小/APP 起点、是否有 VTOR |
| `tools/bl_protocol.py` | **与 C 头保持同步** 的 CAN ID / 命令号 |
| `bootloader/Src/bl_flash.c` | F4 扇区擦写实现 |

## 主机脚本（先可用）

```bash
cd tools
pip install -r requirements.txt
python flash_can.py --bin app.bin --dry-run
python flash_can.py --bin app.bin --interface candlelight --channel 0
```

流程：`GET_INFO → ERASE → SET_ADDR/WRITE_DATA → CRC → JUMP_APP`

## Bootloader 固件（下一步接 Cube）

当前是可编译进工程的**协议 + Flash 抽象骨架**：

1. CubeMX 建 F103C8 工程（CAN1、HSE、晶振按板子）
2. 把 `config/`、`protocol/`、`bootloader/Src|Inc` 加进工程  
   Include：`config`、`config/targets`、`protocol`、`bootloader/Inc`
3. 实现 `bl_can_hw_init/send/recv`（替换 `bl_can.c` 里 weak 空实现）
4. 链接脚本用 `bootloader/linker/stm32f103c8_bl.ld`
5. 应用工程用 `stm32f103c8_app.ld`，向量表在 `0x08004000`，并设置 `VECT_TAB_OFFSET=0x4000`

F103 使用 `SCB->VTOR` 指向 APP；`JUMP_APP` 后直接软跳转。

## 与 DieBieMS 的对应

| DieBieMS | 本工程 |
|----------|--------|
| UART VESC Packet | CAN 8 字节帧 |
| `COMM_ERASE_NEW_APP` | `BL_CMD_ERASE` |
| `COMM_WRITE_NEW_APP_DATA` | `SET_ADDR` + `WRITE_DATA` |
| 暂存区 + 独立 BL 仓 | BL 在 Flash 头，直写 APP 区（64KB 更省空间） |
| DieBieMS-Tool | `tools/flash_can.py` |

## Hex2Bin
由于keil等ide大部分时候都不给出bin，给出mot、hex等文件，目前python脚本只认bin文件，并且bin文件体积也最小，生成的hex文件通过hex2bin.exe转换出来，再使用bin烧录

