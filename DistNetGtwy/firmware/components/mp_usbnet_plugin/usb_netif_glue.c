#include "usb_netif_glue.h"

#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_log.h"
#include "esp_netif.h"
#include "sdkconfig.h"

#if __has_include("py/mpprint.h")
#define MP_USBNET_HAS_MP_PRINT 1
#include "py/mpprint.h"
#else
#define MP_USBNET_HAS_MP_PRINT 0
#endif

static const char *TAG = "usb_netif_glue";
static bool s_running = false;
static esp_netif_t *s_netif = NULL;
static uint8_t s_driver_handle_obj = 0;
static uint32_t s_rx_ok = 0;
static uint32_t s_rx_err = 0;
static uint32_t s_tx_ok = 0;
static uint32_t s_tx_err = 0;

static void usbnet_diag_printf(const char *fmt, ...) {
    char msg[192];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof(msg), fmt, ap);
    va_end(ap);

    printf("[usbnet_glue] %s\n", msg);
}

/*
 * Some integration paths (for example MicroPython USER_C_MODULES-only wiring)
 * may not load this component Kconfig, so CONFIG_MP_USBNET_USB_CLASS_* can be
 * absent. Default to ECM in that case to keep builds working without menuconfig.
 */
#if defined(CONFIG_MP_USBNET_USB_CLASS_ECM) && CONFIG_MP_USBNET_USB_CLASS_ECM
static const usbnet_class_t s_usbnet_class = USBNET_CLASS_ECM;
#elif defined(CONFIG_MP_USBNET_USB_CLASS_RNDIS) && CONFIG_MP_USBNET_USB_CLASS_RNDIS
static const usbnet_class_t s_usbnet_class = USBNET_CLASS_RNDIS;
#else
static const usbnet_class_t s_usbnet_class = USBNET_CLASS_ECM;
#endif

// Provide board-specific TinyUSB wiring in another translation unit to override.
// This function must set up descriptors/endpoints/callbacks for the selected class.
__attribute__((weak)) esp_err_t mp_usbnet_tinyusb_net_start(esp_netif_t *netif, usbnet_class_t usb_class) {
    (void)netif;
    (void)usb_class;
    return ESP_ERR_NOT_SUPPORTED;
}

// Optional board-specific teardown hook.
__attribute__((weak)) esp_err_t mp_usbnet_tinyusb_net_stop(void) {
    return ESP_OK;
}

// Optional board-specific TinyUSB TX hook (lwIP -> USB).
__attribute__((weak)) esp_err_t mp_usbnet_tinyusb_net_tx(const uint8_t *frame, size_t len) {
    (void)frame;
    (void)len;
    return ESP_ERR_NOT_SUPPORTED;
}

static const char *class_name(usbnet_class_t usb_class) {
    switch (usb_class) {
        case USBNET_CLASS_ECM:
            return "ECM";
        case USBNET_CLASS_RNDIS:
            return "RNDIS";
        default:
            return "UNKNOWN";
    }
}

static esp_err_t usbnet_netif_transmit(void *h, void *buffer, size_t len) {
    (void)h;
    return usb_netif_glue_on_lwip_tx((const uint8_t *)buffer, len);
}

static void usbnet_netif_free_rx_buffer(void *h, void *buffer) {
    (void)h;
    free(buffer);
}

esp_err_t usb_netif_glue_start(esp_netif_t *netif) {
    if (!netif) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_running) {
        return ESP_OK;
    }

    const esp_netif_driver_ifconfig_t driver_cfg = {
        .handle = &s_driver_handle_obj,
        .transmit = usbnet_netif_transmit,
        .driver_free_rx_buffer = usbnet_netif_free_rx_buffer,
    };
    esp_err_t err = esp_netif_set_driver_config(netif, &driver_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_netif_set_driver_config failed err=0x%x", (unsigned int)err);
        return err;
    }

    err = mp_usbnet_tinyusb_net_start(netif, s_usbnet_class);
    if (err != ESP_OK) {
        ESP_LOGE(TAG,
                 "TinyUSB net start failed class=%s err=0x%x. "
                 "Implement mp_usbnet_tinyusb_net_start() for your board.",
                 class_name(s_usbnet_class),
                 (unsigned int)err);
        return err;
    }

    s_netif = netif;
    s_rx_ok = 0;
    s_rx_err = 0;
    s_tx_ok = 0;
    s_tx_err = 0;
    esp_netif_action_start(s_netif, 0, 0, NULL);
    esp_netif_action_connected(s_netif, 0, 0, NULL);
    ESP_LOGI(TAG, "usb netif glue started class=%s", class_name(s_usbnet_class));
    usbnet_diag_printf("start class=%s", class_name(s_usbnet_class));
    s_running = true;
    return ESP_OK;
}

esp_err_t usb_netif_glue_stop(void) {
    if (!s_running) {
        return ESP_OK;
    }

    if (s_netif) {
        esp_netif_action_disconnected(s_netif, 0, 0, NULL);
        esp_netif_action_stop(s_netif, 0, 0, NULL);
    }

    esp_err_t err = mp_usbnet_tinyusb_net_stop();
    if (err != ESP_OK) {
        return err;
    }

    s_netif = NULL;
    ESP_LOGI(TAG, "usb netif glue stopped");
    usbnet_diag_printf("stop");
    s_running = false;
    return ESP_OK;
}

esp_err_t usb_netif_glue_on_usb_rx(const uint8_t *frame, size_t len) {
    if (!s_running || !s_netif) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!frame || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    void *copy = malloc(len);
    if (!copy) {
        return ESP_ERR_NO_MEM;
    }
    memcpy(copy, frame, len);

    esp_err_t err = esp_netif_receive(s_netif, copy, len, NULL);
    if (err != ESP_OK) {
        free(copy);
        s_rx_err++;
        ESP_LOGW(TAG, "usb rx->lwip failed err=0x%x len=%u", (unsigned int)err, (unsigned int)len);
    } else {
        s_rx_ok++;
    }
    return err;
}

esp_err_t usb_netif_glue_on_lwip_tx(const uint8_t *frame, size_t len) {
    if (!s_running || !s_netif) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!frame || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err = mp_usbnet_tinyusb_net_tx(frame, len);
    if (err != ESP_OK) {
        s_tx_err++;
        ESP_LOGW(TAG, "lwip tx->usb failed err=0x%x len=%u", (unsigned int)err, (unsigned int)len);
    } else {
        s_tx_ok++;
    }
    return err;
}

void usb_netif_glue_get_stats(uint32_t *rx_ok,
                              uint32_t *rx_err,
                              uint32_t *tx_ok,
                              uint32_t *tx_err) {
    if (rx_ok) {
        *rx_ok = s_rx_ok;
    }
    if (rx_err) {
        *rx_err = s_rx_err;
    }
    if (tx_ok) {
        *tx_ok = s_tx_ok;
    }
    if (tx_err) {
        *tx_err = s_tx_err;
    }
}
