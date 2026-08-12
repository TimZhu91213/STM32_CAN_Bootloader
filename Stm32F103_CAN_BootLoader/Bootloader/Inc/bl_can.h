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

/** True after JUMP_APP: stay in BL until hardware reset / power cycle. */
bool bl_can_hold_until_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* BL_CAN_H */
