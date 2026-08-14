#ifndef BL_CAN_H
#define BL_CAN_H

#include <stdint.h>
#include <stdbool.h>
#include "bl_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

bool bl_can_init(void);
void bl_can_poll(void);   /* call in main loop: rx + protocol state machine */

/** True after any 0x700 command this power cycle (blocks auto-jump at boot). */
bool bl_can_host_seen(void);

/** True after JUMP_APP hold flag (legacy; jump now usually leaves BL). */
bool bl_can_hold_until_reset(void);

/* Board CAN hooks (bl_can_hw_f407.c / bl_can_hw_f103.c) */
bool bl_can_hw_init(void);
bool bl_can_hw_send(uint32_t id, const uint8_t *data, uint8_t dlc);
bool bl_can_hw_recv(uint32_t *id, uint8_t *data, uint8_t *dlc);
void bl_can_hw_heartbeat(void);
void bl_can_hw_stop(void);
uint32_t bl_can_hw_tx_free_level(void);

#ifdef __cplusplus
}
#endif

#endif /* BL_CAN_H */
