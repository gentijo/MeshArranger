#pragma once

#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"
#include "esp_netif.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    USBNET_CLASS_ECM = 0,
    USBNET_CLASS_RNDIS = 1,
} usbnet_class_t;

esp_err_t usb_netif_glue_start(esp_netif_t *netif);
esp_err_t usb_netif_glue_stop(void);

// Call from TinyUSB network receive callback (host->device Ethernet frame).
esp_err_t usb_netif_glue_on_usb_rx(const uint8_t *frame, size_t len);

// Call from lwIP/netif output path to queue device->host Ethernet frame to USB IN.
esp_err_t usb_netif_glue_on_lwip_tx(const uint8_t *frame, size_t len);

void usb_netif_glue_get_stats(uint32_t *rx_ok,
                              uint32_t *rx_err,
                              uint32_t *tx_ok,
                              uint32_t *tx_err);

#ifdef __cplusplus
}
#endif
