#include "usb_netif_glue.h"

#include <stdbool.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_mac.h"

#if __has_include("py/mpprint.h")
#define MP_USBNET_HAS_MP_PRINT 1
#include "py/mpprint.h"
#else
#define MP_USBNET_HAS_MP_PRINT 0
#endif

#if __has_include("tinyusb.h") && __has_include("tinyusb_net.h")
#define MP_USBNET_HAS_ESP_TINYUSB 1
#define MP_USBNET_HAS_TINYUSB_RAW 0
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tinyusb.h"
#include "tinyusb_net.h"
#elif __has_include("tusb.h") && __has_include("class/net/net_device.h")
#define MP_USBNET_HAS_ESP_TINYUSB 0
#define MP_USBNET_HAS_TINYUSB_RAW 1
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tusb.h"
#include "class/net/net_device.h"
#else
#define MP_USBNET_HAS_ESP_TINYUSB 0
#define MP_USBNET_HAS_TINYUSB_RAW 0
#endif

#if MP_USBNET_HAS_TINYUSB_RAW && !(CFG_TUD_ECM_RNDIS || CFG_TUD_NCM)
#undef MP_USBNET_HAS_TINYUSB_RAW
#define MP_USBNET_HAS_TINYUSB_RAW 0
#endif

static const char *TAG = "usb_netif_port";
static bool s_tinyusb_net_started = false;
static const uint8_t s_default_usb_mac[6] = {0x02, 0x00, 0x00, 0x00, 0x00, 0x01};

static inline bool usbnet_is_ipv4_or_arp_frame(const uint8_t *frame, size_t len) {
    if (!frame || len < 14) {
        return false;
    }
    uint16_t ethertype = ((uint16_t)frame[12] << 8) | frame[13];
    return ethertype == 0x0800 || ethertype == 0x0806; // IPv4 or ARP
}

static void usbnet_diag_printf(const char *fmt, ...) {
    char msg[192];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof(msg), fmt, ap);
    va_end(ap);

    printf("[usbnet_port] %s\n", msg);
}

#if MP_USBNET_HAS_TINYUSB_RAW
// Present in MicroPython TinyUSB integration; weak so this component can still
// compile if the symbol isn't linked in a non-MicroPython build.
__attribute__((weak)) void mp_usbd_schedule_task(void);

static inline void usbnet_kick_tinyusb_task(void) {
    if (mp_usbd_schedule_task) {
        mp_usbd_schedule_task();
    }
}

static uint8_t s_raw_tx_frame[1514];
static size_t s_raw_tx_len = 0;
static bool s_raw_tx_queued = false;
static bool s_raw_tx_pending = false;
static bool s_raw_rx_seen = false;
static bool s_raw_rx_suspended = false;
static bool s_raw_rx_renew_pending = false;
static portMUX_TYPE s_raw_lock = portMUX_INITIALIZER_UNLOCKED;
uint8_t tud_network_mac_address[6] = {0x02, 0x00, 0x00, 0x00, 0x00, 0x01};

static void usbnet_raw_try_xmit_queued(void);

void tud_network_init_cb(void) {
    usbnet_diag_printf("tud_network_init_cb");
}

bool tud_network_recv_cb(const uint8_t *src, uint16_t size) {
    if (!s_tinyusb_net_started) {
        if (!s_raw_rx_suspended) {
            usbnet_diag_printf("recv_cb suspended until usbnet.start (last_size=%u)", (unsigned)size);
            s_raw_rx_suspended = true;
        }
        // Return true and intentionally do not renew RX while not started.
        // This back-pressures host traffic so REPL stays responsive.
        return true;
    }
    // Any callback means host-side data interface is active.
    s_raw_rx_seen = true;
    if (!src || size == 0) {
        tud_network_recv_renew();
        return true;
    }

    // Keep this path focused on basic IPv4/ARP. Dropping IPv6/multicast noise
    // avoids starving the tiny single-frame TX queue used by the raw backend.
    if (!usbnet_is_ipv4_or_arp_frame(src, size)) {
        tud_network_recv_renew();
        return true;
    }

    esp_err_t err = usb_netif_glue_on_usb_rx(src, size);
    tud_network_recv_renew();
    return err == ESP_OK;
}

uint16_t tud_network_xmit_cb(uint8_t *dst, void *ref, uint16_t arg) {
    (void)ref;
    (void)arg;
    portENTER_CRITICAL(&s_raw_lock);
    if (!dst || !s_raw_tx_pending || !s_raw_tx_queued || s_raw_tx_len == 0) {
        portEXIT_CRITICAL(&s_raw_lock);
        return 0;
    }

    memcpy(dst, s_raw_tx_frame, s_raw_tx_len);
    uint16_t ret = (uint16_t)s_raw_tx_len;
    s_raw_tx_len = 0;
    s_raw_tx_queued = false;
    s_raw_tx_pending = false;
    portEXIT_CRITICAL(&s_raw_lock);
    return ret;
}

void mp_usbd_post_task_hook(void) {
    if (s_tinyusb_net_started && s_raw_rx_renew_pending && tud_ready()) {
        tud_network_recv_renew();
        s_raw_rx_renew_pending = false;
    }
    usbnet_raw_try_xmit_queued();
}

static void usbnet_raw_try_xmit_queued(void) {
    if (!s_tinyusb_net_started || !tud_ready()) {
        return;
    }

    size_t tx_len = 0;
    bool need_send = false;
    portENTER_CRITICAL(&s_raw_lock);
    if (s_raw_tx_queued && !s_raw_tx_pending && s_raw_tx_len > 0 && s_raw_tx_len <= UINT16_MAX) {
        tx_len = s_raw_tx_len;
        need_send = true;
    }
    portEXIT_CRITICAL(&s_raw_lock);

    if (!need_send || !tud_network_can_xmit((uint16_t)tx_len)) {
        return;
    }

    portENTER_CRITICAL(&s_raw_lock);
    bool can_send_now = s_raw_tx_queued
        && !s_raw_tx_pending
        && s_raw_tx_len == tx_len;
    if (can_send_now) {
        s_raw_tx_pending = true;
    }
    portEXIT_CRITICAL(&s_raw_lock);

    if (can_send_now) {
        tud_network_xmit(NULL, 0);
        // tud_network_xmit() should synchronously invoke tud_network_xmit_cb()
        // before returning. If it doesn't (e.g. internal race where can_xmit
        // changed), clear pending so future retries can proceed.
        portENTER_CRITICAL(&s_raw_lock);
        if (s_raw_tx_pending) {
            s_raw_tx_pending = false;
            portEXIT_CRITICAL(&s_raw_lock);
            ESP_LOGW(TAG, "recovered stale tx pending state len=%u", (unsigned)tx_len);
        } else {
            portEXIT_CRITICAL(&s_raw_lock);
        }
    }
}
#endif

#if MP_USBNET_HAS_ESP_TINYUSB
static esp_err_t tinyusb_rx_callback(void *buffer, uint16_t len, void *ctx) {
    (void)ctx;
    return usb_netif_glue_on_usb_rx((const uint8_t *)buffer, (size_t)len);
}

static void tinyusb_tx_buffer_free(void *buffer, void *ctx) {
    (void)ctx;
    (void)buffer;
}
#endif

esp_err_t mp_usbnet_tinyusb_net_start(esp_netif_t *netif, usbnet_class_t usb_class) {
    if (!netif) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_tinyusb_net_started) {
        return ESP_OK;
    }

    switch (usb_class) {
        case USBNET_CLASS_ECM:
            ESP_LOGI(TAG, "selected USB class: ECM");
            break;
        case USBNET_CLASS_RNDIS:
            ESP_LOGI(TAG, "selected USB class: RNDIS");
            break;
        default:
            return ESP_ERR_INVALID_ARG;
    }

#if MP_USBNET_HAS_ESP_TINYUSB
    const tinyusb_config_t tusb_cfg = {
        .external_phy = false,
    };
    esp_err_t err = tinyusb_driver_install(&tusb_cfg);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "tinyusb_driver_install failed err=0x%x", (unsigned int)err);
        return err;
    }

    tinyusb_net_config_t net_cfg = {
        .on_recv_callback = tinyusb_rx_callback,
        .free_tx_buffer = tinyusb_tx_buffer_free,
        .user_context = NULL,
    };
    esp_err_t mac_err = esp_read_mac(net_cfg.mac_addr, ESP_MAC_WIFI_STA);
    if (mac_err != ESP_OK) {
        ESP_LOGE(TAG, "esp_read_mac failed err=0x%x", (unsigned int)mac_err);
        return mac_err;
    }
    // Ensure locally-administered unicast MAC for USB NIC.
    net_cfg.mac_addr[0] = (uint8_t)((net_cfg.mac_addr[0] | 0x02) & 0xFE);

    err = tinyusb_net_init(TINYUSB_USBDEV_0, &net_cfg);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "tinyusb_net_init failed err=0x%x", (unsigned int)err);
        return err;
    }

    uint8_t lwip_mac[6];
    memcpy(lwip_mac, net_cfg.mac_addr, sizeof(lwip_mac));
    lwip_mac[5] ^= 0x01;
    esp_netif_set_mac(netif, lwip_mac);

    ESP_LOGI(TAG,
            "TinyUSB net started usb-mac=%02x:%02x:%02x:%02x:%02x:%02x",
            net_cfg.mac_addr[0], net_cfg.mac_addr[1], net_cfg.mac_addr[2],
            net_cfg.mac_addr[3], net_cfg.mac_addr[4], net_cfg.mac_addr[5]);
    usbnet_diag_printf("tinyusb_net_start(esp_tinyusb) ok");
    s_tinyusb_net_started = true;
    return ESP_OK;
#elif MP_USBNET_HAS_TINYUSB_RAW
    // TinyUSB MAC is what the host stack uses for the USB NIC address.
    // lwIP MAC must be different from host MAC so ARP source/destination are distinct.
    memcpy(tud_network_mac_address, s_default_usb_mac, sizeof(tud_network_mac_address));
    uint8_t lwip_mac[6];
    memcpy(lwip_mac, tud_network_mac_address, sizeof(lwip_mac));
    lwip_mac[5] = (uint8_t)(lwip_mac[5] + 1);
    if (memcmp(lwip_mac, tud_network_mac_address, sizeof(lwip_mac)) == 0) {
        lwip_mac[5] ^= 0x01;
    }
    esp_netif_set_mac(netif, lwip_mac);

    s_raw_tx_pending = false;
    s_raw_tx_queued = false;
    s_raw_tx_len = 0;
    s_raw_rx_seen = false;
    s_raw_rx_suspended = false;
    s_raw_rx_renew_pending = true;
    // For ECM/RNDIS, TinyUSB calls tud_network_recv_renew() when the host
    // activates the data interface (SET_INTERFACE alt=1). Calling it here can
    // be too early.
    s_tinyusb_net_started = true;
    usbnet_kick_tinyusb_task();
    ESP_LOGI(TAG,
             "TinyUSB raw net started usb-mac=%02x:%02x:%02x:%02x:%02x:%02x lwip-mac=%02x:%02x:%02x:%02x:%02x:%02x",
             tud_network_mac_address[0], tud_network_mac_address[1], tud_network_mac_address[2],
             tud_network_mac_address[3], tud_network_mac_address[4], tud_network_mac_address[5],
             lwip_mac[0], lwip_mac[1], lwip_mac[2], lwip_mac[3], lwip_mac[4], lwip_mac[5]);
    usbnet_diag_printf("tinyusb_net_start(raw) ok");
    return ESP_OK;
#else
    (void)usb_class;
    ESP_LOGE(TAG,
             "No TinyUSB network backend available (need tinyusb_net.h or TinyUSB net_device.h).");
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

esp_err_t mp_usbnet_tinyusb_net_stop(void) {
#if MP_USBNET_HAS_TINYUSB_RAW
    s_raw_tx_pending = false;
    s_raw_tx_queued = false;
    s_raw_tx_len = 0;
    s_raw_rx_seen = false;
    s_raw_rx_suspended = false;
    s_raw_rx_renew_pending = false;
#endif
    s_tinyusb_net_started = false;
    return ESP_OK;
}

esp_err_t mp_usbnet_tinyusb_net_tx(const uint8_t *frame, size_t len) {
#if MP_USBNET_HAS_ESP_TINYUSB
    if (!s_tinyusb_net_started) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!frame || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len > UINT16_MAX) {
        return ESP_ERR_INVALID_SIZE;
    }
    return tinyusb_net_send_sync((void *)frame, (uint16_t)len, NULL, pdMS_TO_TICKS(100));
#elif MP_USBNET_HAS_TINYUSB_RAW
    if (!s_tinyusb_net_started) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!frame || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len > sizeof(s_raw_tx_frame) || len > UINT16_MAX) {
        return ESP_ERR_INVALID_SIZE;
    }

    // Keep this path focused on basic IPv4/ARP so discovery/ping remains reliable.
    if (!usbnet_is_ipv4_or_arp_frame(frame, len)) {
        return ESP_OK;
    }

    // Enqueue one frame from lwIP context. Actual USB submit is drained from
    // mp_usbd_post_task_hook() in TinyUSB task context.
    //
    // If a frame is queued but not pending, replace it with the newest frame
    // so ARP/ICMP retries are not starved by stale traffic.
    for (int i = 0; i < 50; ++i) {
        bool queued_or_replaced = false;
        portENTER_CRITICAL(&s_raw_lock);
        if (!s_raw_tx_pending) {
            memcpy(s_raw_tx_frame, frame, len);
            s_raw_tx_len = len;
            s_raw_tx_queued = true;
            s_raw_tx_pending = false;
            queued_or_replaced = true;
        }
        portEXIT_CRITICAL(&s_raw_lock);
        if (queued_or_replaced) {
            usbnet_kick_tinyusb_task();
            return ESP_OK;
        }
        usbnet_kick_tinyusb_task();
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    ESP_LOGW(TAG, "tx submit timeout len=%u", (unsigned)len);
    return ESP_ERR_TIMEOUT;
#else
    (void)frame;
    (void)len;
    return ESP_ERR_NOT_SUPPORTED;
#endif
}
