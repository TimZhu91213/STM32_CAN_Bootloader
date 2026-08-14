/**
 * @file bl_can_hw_f407.c
 * @brief CAN2 glue for F407 IAP (PB12/PB13), RX ring + TX retry.
 */
#include "bl_config.h"
#include "bl_protocol.h"
#include "can.h"
#include "main.h"
#include <stdbool.h>
#include <string.h>

#define BL_RX_RING_SIZE  16u

typedef struct {
  uint32_t id;
  uint8_t dlc;
  uint8_t data[8];
} bl_can_frame_t;

static volatile uint8_t s_rx_head;
static volatile uint8_t s_rx_tail;
static bl_can_frame_t s_rx_ring[BL_RX_RING_SIZE];
static uint8_t s_session_quiet;

/* Bootloader uses CAN2 as debug/IAP bus */
#define BL_HCAN  hcan2

static void rx_ring_push(uint32_t id, const uint8_t *data, uint8_t dlc)
{
  uint8_t next = (uint8_t)((s_rx_head + 1u) % BL_RX_RING_SIZE);
  if (next == s_rx_tail) {
    return;
  }
  s_rx_ring[s_rx_head].id = id;
  s_rx_ring[s_rx_head].dlc = dlc;
  memcpy(s_rx_ring[s_rx_head].data, data, dlc);
  s_rx_head = next;
}

static void drain_hw_fifo_to_ring(void)
{
  CAN_RxHeaderTypeDef hdr;
  uint8_t rx[8];

  while (HAL_CAN_GetRxFifoFillLevel(&BL_HCAN, CAN_RX_FIFO0) > 0u) {
    if (HAL_CAN_GetRxMessage(&BL_HCAN, CAN_RX_FIFO0, &hdr, rx) != HAL_OK) {
      break;
    }
    if (hdr.IDE != CAN_ID_STD) {
      continue;
    }
    if (hdr.DLC > 8u) {
      hdr.DLC = 8u;
    }
    rx_ring_push(hdr.StdId, rx, (uint8_t)hdr.DLC);
  }
}

void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef *hcanx)
{
  if (hcanx->Instance == CAN2) {
    drain_hw_fifo_to_ring();
  }
}

static void can_recover(void)
{
  CAN_FilterTypeDef f = {0};

  (void)HAL_CAN_Stop(&BL_HCAN);
  f.FilterBank = 14;
  f.FilterScale = CAN_FILTERSCALE_32BIT;
  f.FilterMode = CAN_FILTERMODE_IDMASK;
  f.FilterFIFOAssignment = CAN_FILTER_FIFO0;
  f.FilterIdHigh = 0;
  f.FilterIdLow = 0;
  f.FilterMaskIdHigh = 0;
  f.FilterMaskIdLow = 0;
  f.FilterActivation = CAN_FILTER_ENABLE;
  f.SlaveStartFilterBank = 14;
  (void)HAL_CAN_ConfigFilter(&BL_HCAN, &f);
  (void)HAL_CAN_Start(&BL_HCAN);
  (void)HAL_CAN_ActivateNotification(&BL_HCAN, CAN_IT_RX_FIFO0_MSG_PENDING);
}

bool bl_can_hw_init(void)
{
  CAN_FilterTypeDef f = {0};

  s_rx_head = 0;
  s_rx_tail = 0;
  s_session_quiet = 0;

  f.FilterBank = 14;
  f.FilterScale = CAN_FILTERSCALE_32BIT;
  f.FilterMode = CAN_FILTERMODE_IDMASK;
  f.FilterFIFOAssignment = CAN_FILTER_FIFO0;
  f.FilterIdHigh = 0;
  f.FilterIdLow = 0;
  f.FilterMaskIdHigh = 0;
  f.FilterMaskIdLow = 0;
  f.FilterActivation = CAN_FILTER_ENABLE;
  f.SlaveStartFilterBank = 14;

  if (HAL_CAN_ConfigFilter(&BL_HCAN, &f) != HAL_OK) {
    return false;
  }
  if (HAL_CAN_Start(&BL_HCAN) != HAL_OK) {
    return false;
  }
  if (HAL_CAN_ActivateNotification(&BL_HCAN, CAN_IT_RX_FIFO0_MSG_PENDING) != HAL_OK) {
    return false;
  }
  return true;
}

void bl_can_hw_stop(void)
{
  (void)HAL_CAN_Stop(&BL_HCAN);
}

uint32_t bl_can_hw_tx_free_level(void)
{
  return HAL_CAN_GetTxMailboxesFreeLevel(&BL_HCAN);
}

bool bl_can_hw_send(uint32_t id, const uint8_t *data, uint8_t dlc)
{
  CAN_TxHeaderTypeDef hdr = {0};
  uint8_t tx[8] = {0};
  uint32_t mailbox;
  uint32_t t0;
  uint8_t attempt;

  if (data == 0) {
    return false;
  }
  if (dlc > 8u) {
    dlc = 8u;
  }
  memcpy(tx, data, dlc);

  hdr.StdId = id & 0x7FFu;
  hdr.IDE = CAN_ID_STD;
  hdr.RTR = CAN_RTR_DATA;
  hdr.DLC = dlc;
  hdr.TransmitGlobalTime = DISABLE;

  for (attempt = 0; attempt < 3u; attempt++) {
    uint32_t esr = READ_REG(BL_HCAN.Instance->ESR);
    if ((esr & CAN_ESR_BOFF) != 0u) {
      can_recover();
    }

    t0 = HAL_GetTick();
    while (HAL_CAN_GetTxMailboxesFreeLevel(&BL_HCAN) == 0u) {
      if ((HAL_GetTick() - t0) > 20u) {
        break;
      }
    }
    if (HAL_CAN_GetTxMailboxesFreeLevel(&BL_HCAN) == 0u) {
      continue;
    }

    if (HAL_CAN_AddTxMessage(&BL_HCAN, &hdr, tx, &mailbox) != HAL_OK) {
      continue;
    }

    t0 = HAL_GetTick();
    while (HAL_CAN_IsTxMessagePending(&BL_HCAN, mailbox) != 0u) {
      if ((HAL_GetTick() - t0) > 20u) {
        (void)HAL_CAN_AbortTxRequest(&BL_HCAN, mailbox);
        break;
      }
    }

    if (HAL_CAN_IsTxMessagePending(&BL_HCAN, mailbox) == 0u) {
      esr = READ_REG(BL_HCAN.Instance->ESR);
      if ((esr & CAN_ESR_BOFF) == 0u) {
        return true;
      }
    }
  }
  return false;
}

bool bl_can_hw_recv(uint32_t *id, uint8_t *data, uint8_t *dlc)
{
  if (id == 0 || data == 0 || dlc == 0) {
    return false;
  }

  drain_hw_fifo_to_ring();

  if (s_rx_tail == s_rx_head) {
    return false;
  }

  *id = s_rx_ring[s_rx_tail].id;
  *dlc = s_rx_ring[s_rx_tail].dlc;
  memcpy(data, s_rx_ring[s_rx_tail].data, *dlc);
  s_rx_tail = (uint8_t)((s_rx_tail + 1u) % BL_RX_RING_SIZE);

  if (*id == BL_CAN_ID_CMD) {
    s_session_quiet = 1u;
  }
  return true;
}

void bl_can_hw_heartbeat(void)
{
  static uint32_t last_ms;
  static uint8_t seq;
  uint8_t payload[8] = {0xA5, 0x5A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

  if (s_session_quiet != 0u) {
    return;
  }
  if ((HAL_GetTick() - last_ms) < 2000u) {
    return;
  }
  last_ms = HAL_GetTick();
  payload[2] = seq++;
  (void)bl_can_hw_send(0x7FE, payload, 8);
}
