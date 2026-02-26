#include <inttypes.h>
#include <stdbool.h>

#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_netif_ip_addr.h"
#include "esp_private/usb_phy.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mp_usbnet.h"
#include "nvs_flash.h"
#include "tusb.h"
#include "usb_netif_glue.h"

static const char *TAG = "usbnet_probe";
static usb_phy_handle_t s_phy_hdl;

// Defined by TinyUSB class/net and reused by mp_usbnet_plugin.
extern uint8_t tud_network_mac_address[6];

// Implemented weakly in mp_usbnet_plugin raw backend; call if present.
__attribute__((weak)) void mp_usbd_post_task_hook(void);

static void probe_usb_phy_init(void) {
    const usb_phy_config_t phy_conf = {
        .controller = USB_PHY_CTRL_OTG,
        .otg_mode = USB_OTG_MODE_DEVICE,
        .target = USB_PHY_TARGET_INT,
    };
    ESP_ERROR_CHECK(usb_new_phy(&phy_conf, &s_phy_hdl));
}

static void usb_device_task(void *arg) {
    (void)arg;
    while (true) {
        tud_task();
        if (mp_usbd_post_task_hook) {
            mp_usbd_post_task_hook();
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

static void log_status(void) {
    esp_netif_t *netif = mp_usbnet_get_esp_netif();
    esp_netif_ip_info_t ip_info = {0};
    if (netif && esp_netif_get_ip_info(netif, &ip_info) == ESP_OK) {
        ESP_LOGI(TAG, "ifconfig ip=" IPSTR " mask=" IPSTR " gw=" IPSTR,
                 IP2STR(&ip_info.ip), IP2STR(&ip_info.netmask), IP2STR(&ip_info.gw));
    }

    uint32_t rx_ok = 0;
    uint32_t rx_err = 0;
    uint32_t tx_ok = 0;
    uint32_t tx_err = 0;
    usb_netif_glue_get_stats(&rx_ok, &rx_err, &tx_ok, &tx_err);
    ESP_LOGI(TAG, "stats rx_ok=%" PRIu32 " rx_err=%" PRIu32 " tx_ok=%" PRIu32 " tx_err=%" PRIu32,
             rx_ok, rx_err, tx_ok, tx_err);
}

void app_main(void) {
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    } else {
        ESP_ERROR_CHECK(err);
    }

    ESP_ERROR_CHECK(esp_netif_init());
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(err);
    }

    // Set a deterministic locally-administered MAC before descriptor reads.
    ESP_ERROR_CHECK(esp_read_mac(tud_network_mac_address, ESP_MAC_WIFI_STA));
    tud_network_mac_address[0] = (uint8_t)((tud_network_mac_address[0] | 0x02) & 0xFE);

    probe_usb_phy_init();

    if (!tusb_init()) {
        ESP_LOGE(TAG, "tusb_init failed");
        return;
    }

    BaseType_t task_ok = xTaskCreatePinnedToCore(
        usb_device_task,
        "usb_task",
        4096,
        NULL,
        20,
        NULL,
        0
    );
    if (task_ok != pdPASS) {
        ESP_LOGE(TAG, "failed to create usb task");
        return;
    }

    err = mp_usbnet_start("usbnet-probe", "192.168.137.2", "255.255.255.0", "192.168.137.1");
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "mp_usbnet_start failed err=0x%x", (unsigned int)err);
        return;
    }

    ESP_LOGI(TAG, "standalone probe started; host should configure usb0=192.168.137.1/24 and ping 192.168.137.2");

    while (true) {
        log_status();
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}

