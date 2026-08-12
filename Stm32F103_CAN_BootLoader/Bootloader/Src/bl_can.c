/**
 * CAN protocol state machine (hardware RX/TX left as board hooks).
 *
 * Integrate with your CubeMX CAN:
 *   - implement bl_can_hw_send() / bl_can_hw_recv() below
 *   - call bl_can_poll() from main loop
 */
#include "bl_can.h"
#include "bl_config.h"
#include "bl_flash.h"
#include "bl_crc.h"
#include "main.h"
#include "can.h"

#include <string.h>

/* Implemented in bl_can_hw_f103.c */
bool bl_can_hw_init(void); /* may be called again after erase to restore RX IRQ */
bool bl_can_hw_send(uint32_t id, const uint8_t *data, uint8_t dlc);
bool bl_can_hw_recv(uint32_t *id, uint8_t *data, uint8_t *dlc);
void bl_can_hw_heartbeat(void);

typedef enum {
    ST_IDLE = 0,
    ST_WRITING,
} bl_session_state_t;

static bl_session_state_t s_state = ST_IDLE;
static uint32_t s_write_addr = BL_APP_START_ADDR;
static uint32_t s_image_size = 0;
static uint32_t s_bytes_written = 0;
static uint8_t s_last_write_seq = 0xFFu;
static uint8_t s_have_write_seq = 0;
static uint8_t s_host_seen = 0;
static uint8_t s_hold_until_reset = 0;

static void send_rsp_once(uint8_t cmd, uint8_t status, const uint8_t *extra, uint8_t extra_len)
{
    uint8_t frame[8] = {0};
    uint32_t t0;

    frame[0] = cmd;
    frame[1] = status;
    if (extra != 0 && extra_len > 0u) {
        if (extra_len > 6u) {
            extra_len = 6u;
        }
        memcpy(&frame[2], extra, extra_len);
    }

    t0 = HAL_GetTick();
    while (HAL_CAN_GetTxMailboxesFreeLevel(&hcan) < 3u) {
        if ((HAL_GetTick() - t0) > 50u) {
            break;
        }
    }

    HAL_Delay(BL_CAN_TX_GAP_MS);
    (void)bl_can_hw_send(BL_CAN_ID_RSP, frame, 8u);
    HAL_Delay(BL_CAN_TX_GAP_MS);
}

static void send_rsp(uint8_t cmd, uint8_t status, const uint8_t *extra, uint8_t extra_len)
{
    send_rsp_once(cmd, status, extra, extra_len);
}

static void handle_get_info(void)
{
    uint8_t extra[6];
    extra[0] = (uint8_t)BL_PROTOCOL_VERSION;
    extra[1] = (uint8_t)BL_FW_VERSION_MAJOR;
    extra[2] = (uint8_t)BL_FW_VERSION_MINOR;
    extra[3] = (uint8_t)(BL_INFO_MAGIC & 0xFFu);
    extra[4] = (uint8_t)((BL_INFO_MAGIC >> 8) & 0xFFu);
    extra[5] = (uint8_t)((BL_INFO_MAGIC >> 16) & 0xFFu);
    /* Single reply — double TX added bus contention / stuff errors */
    send_rsp(BL_CMD_GET_INFO, BL_STATUS_OK, extra, 6);
}

static void handle_erase(const uint8_t *payload, uint8_t len)
{
    if (len < 4u) {
        send_rsp(BL_CMD_ERASE, BL_STATUS_ERR_PARAM, 0, 0);
        return;
    }
    uint32_t size = (uint32_t)payload[0] | ((uint32_t)payload[1] << 8) |
                    ((uint32_t)payload[2] << 16) | ((uint32_t)payload[3] << 24);

    HAL_Delay(BL_CAN_TX_GAP_MS);

    if (!bl_flash_erase_app(size)) {
        send_rsp(BL_CMD_ERASE, BL_STATUS_ERR_FLASH, 0, 0);
        return;
    }
    s_image_size = size;
    s_bytes_written = 0;
    s_write_addr = BL_APP_START_ADDR;
    s_state = ST_IDLE;

    HAL_Delay(BL_CAN_TX_GAP_MS);
    send_rsp(BL_CMD_ERASE, BL_STATUS_OK, 0, 0);
}

static void handle_set_addr(const uint8_t *payload, uint8_t len)
{
    if (len < 4u) {
        send_rsp(BL_CMD_SET_ADDR, BL_STATUS_ERR_PARAM, 0, 0);
        return;
    }
    uint32_t offset = (uint32_t)payload[0] | ((uint32_t)payload[1] << 8) |
                      ((uint32_t)payload[2] << 16) | ((uint32_t)payload[3] << 24);
    if (offset >= BL_APP_MAX_SIZE) {
        send_rsp(BL_CMD_SET_ADDR, BL_STATUS_ERR_PARAM, 0, 0);
        return;
    }
    s_write_addr = BL_APP_START_ADDR + offset;
    s_bytes_written = offset;
    s_state = ST_WRITING;
    s_have_write_seq = 0;
    s_last_write_seq = 0xFFu;
    send_rsp(BL_CMD_SET_ADDR, BL_STATUS_OK, 0, 0);
}

static void handle_write_data(const uint8_t *payload, uint8_t len)
{
    uint8_t seq;
    uint8_t dlen;
    const uint8_t *data;
    uint8_t ack_extra[1];

    /* Layout: [seq][data...]  — host matches ACK.seq to avoid retry desync */
    if (s_state != ST_WRITING || len < 2u || len > (BL_CAN_DATA_BYTES + 1u)) {
        send_rsp(BL_CMD_WRITE_DATA, BL_STATUS_ERR_STATE, 0, 0);
        return;
    }

    seq = payload[0];
    data = &payload[1];
    dlen = (uint8_t)(len - 1u);
    ack_extra[0] = seq;

    /* Duplicate (late retry): do not re-program flash, just re-ACK */
    if ((s_have_write_seq != 0u) && (seq == s_last_write_seq)) {
        send_rsp(BL_CMD_WRITE_DATA, BL_STATUS_OK, ack_extra, 1);
        return;
    }

    if (!bl_flash_program(s_write_addr, data, dlen)) {
        send_rsp(BL_CMD_WRITE_DATA, BL_STATUS_ERR_FLASH, ack_extra, 1);
        return;
    }
    s_write_addr += dlen;
    s_bytes_written += dlen;
    s_last_write_seq = seq;
    s_have_write_seq = 1u;
    send_rsp(BL_CMD_WRITE_DATA, BL_STATUS_OK, ack_extra, 1);
}

static void handle_crc(const uint8_t *payload, uint8_t len)
{
    if (len < 4u || s_image_size == 0u) {
        send_rsp(BL_CMD_CRC, BL_STATUS_ERR_PARAM, 0, 0);
        return;
    }
    if (!bl_flash_flush_pending()) {
        send_rsp(BL_CMD_CRC, BL_STATUS_ERR_FLASH, 0, 0);
        return;
    }
    uint32_t expect = (uint32_t)payload[0] | ((uint32_t)payload[1] << 8) |
                      ((uint32_t)payload[2] << 16) | ((uint32_t)payload[3] << 24);
    uint32_t actual = bl_crc32_flash(s_image_size);
    if (actual != expect) {
        send_rsp(BL_CMD_CRC, BL_STATUS_ERR_CRC, 0, 0);
        return;
    }
    send_rsp(BL_CMD_CRC, BL_STATUS_OK, 0, 0);
}

static void handle_frame(const uint8_t *data, uint8_t dlc)
{
    if (dlc < 1u) {
        return;
    }
    uint8_t cmd = data[0];
    const uint8_t *payload = &data[1];
    uint8_t plen = (uint8_t)(dlc - 1u);

    s_host_seen = 1u;

    switch (cmd) {
    case BL_CMD_GET_INFO:
        handle_get_info();
        break;
    case BL_CMD_ERASE:
        handle_erase(payload, plen);
        break;
    case BL_CMD_SET_ADDR:
        handle_set_addr(payload, plen);
        break;
    case BL_CMD_WRITE_DATA:
        handle_write_data(payload, plen);
        break;
    case BL_CMD_CRC:
        handle_crc(payload, plen);
        break;
    case BL_CMD_JUMP_APP:
        /* Do not soft-jump: ACK and idle until power cycle / NRST.
         * APP is entered only from main() after a clean reset. */
        (void)bl_flash_flush_pending();
        s_state = ST_IDLE;
        s_hold_until_reset = 1u;
        send_rsp(BL_CMD_JUMP_APP, BL_STATUS_OK, 0, 0);
        break;
    case BL_CMD_ABORT:
        s_state = ST_IDLE;
        s_image_size = 0;
        send_rsp(BL_CMD_ABORT, BL_STATUS_OK, 0, 0);
        break;
    default:
        send_rsp(cmd, BL_STATUS_ERR_UNKNOWN, 0, 0);
        break;
    }
}

bool bl_can_init(void)
{
    s_state = ST_IDLE;
    s_write_addr = BL_APP_START_ADDR;
    s_image_size = 0;
    s_bytes_written = 0;
    s_have_write_seq = 0;
    s_last_write_seq = 0xFFu;
    s_host_seen = 0;
    s_hold_until_reset = 0;
    return bl_can_hw_init();
}

bool bl_can_host_seen(void)
{
    return (s_host_seen != 0u);
}

bool bl_can_hold_until_reset(void)
{
    return (s_hold_until_reset != 0u);
}

void bl_can_poll(void)
{
    uint32_t id = 0;
    uint8_t data[8];
    uint8_t dlc = 0;
    while (bl_can_hw_recv(&id, data, &dlc)) {
        if (id == BL_CAN_ID_CMD) {
            handle_frame(data, dlc);
        }
    }
    /* No heartbeat during update or after JUMP (waiting for power cycle) */
    if (s_hold_until_reset == 0u && s_image_size == 0u && s_state == ST_IDLE) {
        bl_can_hw_heartbeat();
    }
}
