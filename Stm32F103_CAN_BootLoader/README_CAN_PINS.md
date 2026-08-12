# CAN 接线

| 功能 | 引脚 |
|------|------|
| CAN_RX | **PA11** |
| CAN_TX | **PA12** |

波特率 500 kbit/s。总线两端终端电阻各 120Ω。

## 运行时

- Bootloader 协议：CMD `0x700` / RSP `0x701`
- 存活帧：每 **1s** 发一帧 **StdId `0x7FE`**，数据 `A5 5A seq ...`；PC13 随心跳翻转
