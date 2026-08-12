/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    can.c
  ******************************************************************************
  */
/* USER CODE END Header */
#include "can.h"

CAN_HandleTypeDef hcan;

void MX_CAN_Init(void)
{
  hcan.Instance = CAN1;
  /* 500 kbit/s @ APB1=36MHz: 36e6/(4*(1+15+2))=500000, sample≈88.9%, SJW<=BS2 */
  hcan.Init.Prescaler = 4;
#if CAN_LOOPBACK_TEST
  hcan.Init.Mode = CAN_MODE_LOOPBACK;
#else
  hcan.Init.Mode = CAN_MODE_NORMAL;
#endif
  hcan.Init.SyncJumpWidth = CAN_SJW_2TQ;
  hcan.Init.TimeSeg1 = CAN_BS1_15TQ;
  hcan.Init.TimeSeg2 = CAN_BS2_2TQ;
  hcan.Init.TimeTriggeredMode = DISABLE;
  hcan.Init.AutoBusOff = ENABLE;
  hcan.Init.AutoWakeUp = DISABLE;
  /* With PCAN ACK present: retransmit until success — cuts lost 0x701 replies */
  hcan.Init.AutoRetransmission = ENABLE;
  hcan.Init.ReceiveFifoLocked = DISABLE;
  hcan.Init.TransmitFifoPriority = DISABLE;
  if (HAL_CAN_Init(&hcan) != HAL_OK) {
    Error_Handler();
  }
}

void HAL_CAN_MspInit(CAN_HandleTypeDef* canHandle)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  if (canHandle->Instance == CAN1) {
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_RCC_CAN1_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();

    CLEAR_BIT(AFIO->MAPR, AFIO_MAPR_CAN_REMAP);

    GPIO_InitStruct.Pin = GPIO_PIN_11;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_12;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    HAL_NVIC_SetPriority(USB_LP_CAN1_RX0_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(USB_LP_CAN1_RX0_IRQn);
    HAL_NVIC_SetPriority(USB_HP_CAN1_TX_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(USB_HP_CAN1_TX_IRQn);
  }
}

void HAL_CAN_MspDeInit(CAN_HandleTypeDef* canHandle)
{
  if (canHandle->Instance == CAN1) {
    __HAL_RCC_CAN1_CLK_DISABLE();
    HAL_GPIO_DeInit(GPIOA, GPIO_PIN_11 | GPIO_PIN_12);
    HAL_NVIC_DisableIRQ(USB_LP_CAN1_RX0_IRQn);
    HAL_NVIC_DisableIRQ(USB_HP_CAN1_TX_IRQn);
  }
}
