#ifndef BL_APP_JUMP_H
#define BL_APP_JUMP_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Returns true if stack pointer + reset vector look valid. */
bool bl_app_is_valid(void);

/** Never returns on success. */
void bl_app_jump(void);

#ifdef __cplusplus
}
#endif

#endif /* BL_APP_JUMP_H */
