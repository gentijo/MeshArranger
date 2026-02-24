#include "usb_netif_glue.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "esp_log.h"
#include "esp_mac.h"

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
static portMUX_TYPE s_raw_lock = portMUX_INITIALIZER_UNLOCKED;
uint8_t tud_network_mac_address[6] = {0x02, 0x00, 0x00, 0x00, 0x00, 0x01};

static void usbnet_raw_try_xmit_queued(void);

void tud_network_init_cb(void) {
}

bool tud_network_recv_cb(const uint8_t *src, uint16_t size) {
    if (!s_tinyusb_net_started) {
        tud_network_recv_renew();
        return false;
    }
    s_raw_rx_seen = true;
    // #region agent log
    if (src && size > 0) {
        ESP_LOGI(TAG, "AGENTLOG H=A loc=recv_cb rx_seen=1 size=%u", (unsigned)size);
    }
    // #endregion
    if (!src || size == 0) {
        usbnet_raw_try_xmit_queued();
        tud_network_recv_renew();
        return true;
    }

    esp_err_t err = usb_netif_glue_on_usb_rx(src, size);
    usbnet_raw_try_xmit_queued();
    tud_network_recv_renew();
    return err == ESP_OK;
}

uint16_t tud_network_xmit_cb(uint8_t *dst, void *ref, uint16_t arg) {
    (void)ref;
    (void)arg;
    portENTER_CRITICAL(&s_raw_lock);
    if (!dst || !s_raw_tx_pending || !s_raw_tx_queued || s_raw_tx_len == 0) {
        // #region agent log
        ESP_LOGI(TAG, "AGENTLOG H=C loc=xmit_cb skip=1 dst=%d pending=%d queued=%d len=%u",
                 dst ? 1 : 0, s_raw_tx_pending ? 1 : 0, s_raw_tx_queued ? 1 : 0, (unsigned)s_raw_tx_len);
        // #endregion
        portEXIT_CRITICAL(&s_raw_lock);
        return 0;
    }

    memcpy(dst, s_raw_tx_frame, s_raw_tx_len);
    uint16_t ret = (uint16_t)s_raw_tx_len;
    s_raw_tx_len = 0;
    s_raw_tx_queued = false;
    s_raw_tx_pending = false;
    portEXIT_CRITICAL(&s_raw_lock);
    // #region agent log
    ESP_LOGI(TAG, "AGENTLOG H=C loc=xmit_cb ret=%u", (unsigned)ret);
    // #endregion
    return ret;
}

void mp_usbd_post_task_hook(void) {
    usbnet_raw_try_xmit_queued();
}

static void usbnet_raw_try_xmit_queued(void) {
    if (!s_tinyusb_net_started || !tud_ready()) {
        // #region agent log
        if (s_raw_tx_queued) {
            ESP_LOGI(TAG, "AGENTLOG H=B loc=try_xmit skip=not_started_or_not_ready started=%d ready=%d",
                     s_tinyusb_net_started ? 1 : 0, tud_ready() ? 1 : 0);
        }
        // #endregion
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
        // #region agent log
        if (need_send) {
            ESP_LOGI(TAG, "AGENTLOG H=B loc=try_xmit skip=can_xmit_false tx_len=%u can_xmit=%d",
                     (unsigned)tx_len, tud_network_can_xmit((uint16_t)tx_len) ? 1 : 0);
        }
        // #endregion
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
        // #region agent log
        ESP_LOGI(TAG, "AGENTLOG H=B loc=try_xmit calling_tud_network_xmit tx_len=%u", (unsigned)tx_len);
        // #endregion
        tud_network_xmit(NULL, 0);
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
    s_tinyusb_net_started = true;
    return ESP_OK;
#elif MP_USBNET_HAS_TINYUSB_RAW
    esp_err_t mac_err = esp_read_mac(tud_network_mac_address, ESP_MAC_WIFI_STA);
    if (mac_err != ESP_OK) {
        ESP_LOGE(TAG, "esp_read_mac failed err=0x%x", (unsigned int)mac_err);
        return mac_err;
    }
    tud_network_mac_address[0] = (uint8_t)((tud_network_mac_address[0] | 0x02) & 0xFE);

    uint8_t lwip_mac[6];
    memcpy(lwip_mac, tud_network_mac_address, sizeof(lwip_mac));
    lwip_mac[5] ^= 0x01;
    esp_netif_set_mac(netif, lwip_mac);

    s_raw_tx_pending = false;
    s_raw_tx_queued = false;
    s_raw_tx_len = 0;
    s_raw_rx_seen = false;
#if CFG_TUD_NCM
    tud_network_link_state(0, true);
#endif
    // For ECM/RNDIS, TinyUSB calls tud_network_recv_renew() when the host
    // activates the data interface (SET_INTERFACE alt=1). Calling it here can
    // be too early.
    s_tinyusb_net_started = true;
    ESP_LOGI(TAG,
             "TinyUSB raw net started mac=%02x:%02x:%02x:%02x:%02x:%02x",
             tud_network_mac_address[0], tud_network_mac_address[1], tud_network_mac_address[2],
             tud_network_mac_address[3], tud_network_mac_address[4], tud_network_mac_address[5]);
    return ESP_OK;
#else
    (void)usb_class;
    ESP_LOGE(TAG,
             "No TinyUSB network backend available (need tinyusb_net.h or TinyUSB net_device.h).");
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

esp_err_t mp_usbnet_tinyusb_net_stop(void) {
#if MP_USBNET_HAS_TINYUSB_RAW && CFG_TUD_NCM
    tud_network_link_state(0, false);
#endif
#if MP_USBNET_HAS_TINYUSB_RAW
    s_raw_tx_pending = false;
    s_raw_tx_queued = false;
    s_raw_tx_len = 0;
    s_raw_rx_seen = false;
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

    if (!tud_ready() || !s_raw_rx_seen) {
        // #region agent log
        ESP_LOGI(TAG, "AGENTLOG H=A loc=tinyusb_net_tx reject ready=%d rx_seen=%d len=%u",
                 tud_ready() ? 1 : 0, s_raw_rx_seen ? 1 : 0, (unsigned)len);
        // #endregion
        return ESP_ERR_INVALID_STATE;
    }

    // Enqueue one frame from lwIP context; actual transmit is drained from
    // TinyUSB callback context (recv + scheduled mp_usbd task hook) to avoid
    // cross-context races.
    for (int i = 0; i < 100; ++i) {
        bool queued = false;
        portENTER_CRITICAL(&s_raw_lock);
        if (!s_raw_tx_queued && !s_raw_tx_pending) {
            memcpy(s_raw_tx_frame, frame, len);
            s_raw_tx_len = len;
            s_raw_tx_queued = true;
            s_raw_tx_pending = false;
            queued = true;
        }
        portEXIT_CRITICAL(&s_raw_lock);
        if (queued) {
            // #region agent log
            ESP_LOGI(TAG, "AGENTLOG H=A loc=tinyusb_net_tx queued=1 len=%u iter=%d", (unsigned)len, i);
            // #endregion
            usbnet_kick_tinyusb_task();
            return ESP_OK;
        }
        usbnet_kick_tinyusb_task();
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    // #region agent log
    ESP_LOGI(TAG, "AGENTLOG H=A loc=tinyusb_net_tx timeout=1 len=%u", (unsigned)len);
    // #endregion
    return ESP_ERR_TIMEOUT;
#else
    (void)frame;
    (void)len;
    return ESP_ERR_NOT_SUPPORTED;
#endif
}
