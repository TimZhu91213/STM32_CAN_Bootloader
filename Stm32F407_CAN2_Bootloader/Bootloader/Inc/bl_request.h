#ifndef BL_REQUEST_H
#define BL_REQUEST_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/** If APP set shared magic then reset, clear it and return true → stay in BL. */
bool bl_request_consume_update_flag(void);

#ifdef __cplusplus
}
#endif

#endif /* BL_REQUEST_H */
