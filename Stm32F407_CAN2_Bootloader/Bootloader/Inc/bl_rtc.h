/**
 * @file bl_rtc.h
 * @brief Set RTC calendar from Unix timestamp (F407 + LSE).
 */
#ifndef BL_RTC_H
#define BL_RTC_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

bool bl_rtc_set_from_unix(uint32_t unix_ts);

#ifdef __cplusplus
}
#endif

#endif /* BL_RTC_H */
