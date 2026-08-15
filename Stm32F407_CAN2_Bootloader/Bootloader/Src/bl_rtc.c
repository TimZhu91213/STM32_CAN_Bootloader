/**
 * @file bl_rtc.c
 * @brief Set RTC calendar from Unix timestamp (uses Cube MX_RTC_Init / hrtc).
 */
#include "bl_rtc.h"
#include "bl_config.h"
#include "rtc.h"

typedef struct {
    uint16_t year;
    uint8_t month;
    uint8_t day;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
    uint8_t weekday;
} bl_rtc_cal_t;

static uint8_t is_leap_year(uint16_t year)
{
    return (((year % 4U) == 0U) && ((year % 100U) != 0U)) || ((year % 400U) == 0U) ? 1U : 0U;
}

static uint8_t days_in_month(uint16_t year, uint8_t month)
{
    static const uint8_t dim[] = {31U, 28U, 31U, 30U, 31U, 30U, 31U, 31U, 30U, 31U, 30U, 31U};

    if ((month < 1U) || (month > 12U)) {
        return 0U;
    }
    if (month == 2U) {
        return (uint8_t)(28U + is_leap_year(year));
    }
    return dim[month - 1U];
}

static void unix_to_calendar(uint32_t unix_ts, bl_rtc_cal_t *cal)
{
    uint32_t days;
    uint32_t sod;
    uint16_t year;

    if (cal == NULL) {
        return;
    }

    days = unix_ts / 86400U;
    sod = unix_ts % 86400U;
    cal->hour = (uint8_t)(sod / 3600U);
    sod %= 3600U;
    cal->minute = (uint8_t)(sod / 60U);
    cal->second = (uint8_t)(sod % 60U);

    /* 1970-01-01 was Thursday (RTC_WEEKDAY_THURSDAY = 0x05). */
    cal->weekday = (uint8_t)(((days + 4U) % 7U) + 1U);

    year = 1970U;
    while (1U) {
        uint32_t diy = 365U;
        if (is_leap_year(year) != 0U) {
            diy = 366U;
        }
        if (days < diy) {
            break;
        }
        days -= diy;
        year++;
    }

    cal->year = year;
    cal->month = 1U;
    while (cal->month <= 12U) {
        uint8_t dim = days_in_month(year, cal->month);
        if (days < dim) {
            break;
        }
        days -= dim;
        cal->month++;
    }
    cal->day = (uint8_t)(days + 1U);
}

bool bl_rtc_set_from_unix(uint32_t unix_ts)
{
    bl_rtc_cal_t cal;
    RTC_TimeTypeDef s_time = {0};
    RTC_DateTypeDef s_date = {0};

    unix_to_calendar(unix_ts, &cal);
    if ((cal.year < 2000U) || (cal.year > 2099U)) {
        return false;
    }

    s_time.Hours = cal.hour;
    s_time.Minutes = cal.minute;
    s_time.Seconds = cal.second;
    s_time.DayLightSaving = RTC_DAYLIGHTSAVING_NONE;
    s_time.StoreOperation = RTC_STOREOPERATION_RESET;

    s_date.Year = (uint8_t)(cal.year - 2000U);
    s_date.Month = cal.month;
    s_date.Date = cal.day;
    s_date.WeekDay = cal.weekday;

    HAL_PWR_EnableBkUpAccess();
    if (HAL_RTC_SetTime(&hrtc, &s_time, RTC_FORMAT_BIN) != HAL_OK) {
        return false;
    }
    if (HAL_RTC_SetDate(&hrtc, &s_date, RTC_FORMAT_BIN) != HAL_OK) {
        return false;
    }
    HAL_RTCEx_BKUPWrite(&hrtc, BL_RTC_BKP_REG, BL_RTC_BKP_MAGIC);

    return true;
}
