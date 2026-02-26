#include "mp_usbnet.h"

#include <stdbool.h>
#include <string.h>
#include <stdio.h>

#include "esp_log.h"
#include "esp_netif_defaults.h"
#include "esp_netif_ip_addr.h"
#include "usb_netif_glue.h"
#include "lwip/ip_addr.h"

#if __has_include("py/obj.h") && __has_include("py/runtime.h")
#define MP_USBNET_ENABLE_MICROPY_BINDINGS (1)
#include "py/obj.h"
#include "py/runtime.h"
#else
#define MP_USBNET_ENABLE_MICROPY_BINDINGS (0)
#endif

static const char *TAG = "mp_usbnet";

static esp_netif_t *s_netif = NULL;
static bool s_up = false;

static esp_err_t set_static_ipv4(esp_netif_t *netif,
                                 const char *ip,
                                 const char *netmask,
                                 const char *gateway) {
    esp_netif_ip_info_t ip_info = {0};

    if (esp_netif_str_to_ip4(ip, &ip_info.ip) != ESP_OK ||
        esp_netif_str_to_ip4(netmask, &ip_info.netmask) != ESP_OK ||
        esp_netif_str_to_ip4(gateway, &ip_info.gw) != ESP_OK) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err = esp_netif_dhcpc_stop(netif);
    if (err != ESP_OK && err != ESP_ERR_ESP_NETIF_DHCP_ALREADY_STOPPED) {
        return err;
    }
    return esp_netif_set_ip_info(netif, &ip_info);
}

esp_err_t mp_usbnet_start(const char *hostname,
                          const char *ip,
                          const char *netmask,
                          const char *gateway) {
    if (s_up) {
        return ESP_OK;
    }

    if (!hostname || !ip || !netmask || !gateway) {
        return ESP_ERR_INVALID_ARG;
    }

    // Ensure lwIP/tcpip stack is initialized before any RX frame is delivered
    // via esp_netif_receive().
    esp_err_t err = esp_netif_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;
    }

    esp_netif_inherent_config_t base_cfg = ESP_NETIF_INHERENT_DEFAULT_ETH();
    base_cfg.flags = (esp_netif_flags_t)(base_cfg.flags & ~ESP_NETIF_DHCP_CLIENT);
    base_cfg.if_key = "USBNET_DEF";
    base_cfg.if_desc = "usbnet";

    esp_netif_config_t cfg = {
        .base = &base_cfg,
        .driver = NULL,
        .stack = ESP_NETIF_NETSTACK_DEFAULT_ETH,
    };
    s_netif = esp_netif_new(&cfg);
    if (!s_netif) {
        return ESP_FAIL;
    }

    err = esp_netif_set_hostname(s_netif, hostname);
    if (err != ESP_OK) {
        goto fail;
    }

    err = set_static_ipv4(s_netif, ip, netmask, gateway);
    if (err != ESP_OK) {
        goto fail;
    }

    err = usb_netif_glue_start(s_netif);
    if (err != ESP_OK) {
        goto fail;
    }

    // Enforce final static IPv4 after netif bring-up.
    err = set_static_ipv4(s_netif, ip, netmask, gateway);
    if (err != ESP_OK) {
        usb_netif_glue_stop();
        goto fail;
    }

    esp_netif_ip_info_t ip_info = {0};
    if (esp_netif_get_ip_info(s_netif, &ip_info) == ESP_OK) {
        ESP_LOGI(TAG, "USB netif IPv4 " IPSTR " netmask " IPSTR " gw " IPSTR,
                 IP2STR(&ip_info.ip), IP2STR(&ip_info.netmask), IP2STR(&ip_info.gw));
    }

    s_up = true;
    ESP_LOGI(TAG, "USB netif started hostname=%s ip=%s", hostname, ip);
    return ESP_OK;

fail:
    if (s_netif) {
        esp_netif_destroy(s_netif);
        s_netif = NULL;
    }
    return err;
}

esp_err_t mp_usbnet_stop(void) {
    if (!s_up) {
        return ESP_OK;
    }

    esp_err_t err = usb_netif_glue_stop();
    if (err != ESP_OK) {
        return err;
    }
    if (s_netif) {
        esp_netif_destroy(s_netif);
        s_netif = NULL;
    }

    s_up = false;
    return ESP_OK;
}

bool mp_usbnet_is_up(void) {
    return s_up;
}

esp_netif_t *mp_usbnet_get_esp_netif(void) {
    return s_netif;
}

#if MP_USBNET_ENABLE_MICROPY_BINDINGS
// ---- MicroPython module bindings ----

static mp_obj_t mp_usbnet_start_py(size_t n_args, const mp_obj_t *args) {
    const char *hostname = mp_obj_str_get_str(args[0]);
    const char *ip = mp_obj_str_get_str(args[1]);
    const char *netmask = mp_obj_str_get_str(args[2]);
    const char *gateway = mp_obj_str_get_str(args[3]);

    esp_err_t err = mp_usbnet_start(hostname, ip, netmask, gateway);
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("usbnet start failed: %d"),
                          err);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_usbnet_start_obj, 4, 4, mp_usbnet_start_py);

static mp_obj_t mp_usbnet_stop_py(void) {
    esp_err_t err = mp_usbnet_stop();
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("usbnet stop failed: %d"),
                          err);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usbnet_stop_obj, mp_usbnet_stop_py);

static mp_obj_t mp_usbnet_is_up_py(void) {
    return mp_obj_new_bool(mp_usbnet_is_up());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usbnet_is_up_obj, mp_usbnet_is_up_py);

static mp_obj_t mp_usbnet_ifconfig_py(void) {
    if (!s_netif) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("usbnet not started"));
    }

    esp_netif_ip_info_t ip_info = {0};
    esp_err_t err = esp_netif_get_ip_info(s_netif, &ip_info);
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("usbnet ifconfig failed: %d"),
                          err);
    }

    char ip[16];
    char netmask[16];
    char gateway[16];
    snprintf(ip, sizeof(ip), IPSTR, IP2STR(&ip_info.ip));
    snprintf(netmask, sizeof(netmask), IPSTR, IP2STR(&ip_info.netmask));
    snprintf(gateway, sizeof(gateway), IPSTR, IP2STR(&ip_info.gw));

    mp_obj_t tuple[3] = {
        mp_obj_new_str(ip, strlen(ip)),
        mp_obj_new_str(netmask, strlen(netmask)),
        mp_obj_new_str(gateway, strlen(gateway)),
    };
    return mp_obj_new_tuple(3, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usbnet_ifconfig_obj, mp_usbnet_ifconfig_py);

static mp_obj_t mp_usbnet_stats_py(void) {
    uint32_t rx_ok = 0;
    uint32_t rx_err = 0;
    uint32_t tx_ok = 0;
    uint32_t tx_err = 0;
    usb_netif_glue_get_stats(&rx_ok, &rx_err, &tx_ok, &tx_err);

    mp_obj_t tuple[4] = {
        mp_obj_new_int_from_uint(rx_ok),
        mp_obj_new_int_from_uint(rx_err),
        mp_obj_new_int_from_uint(tx_ok),
        mp_obj_new_int_from_uint(tx_err),
    };
    return mp_obj_new_tuple(4, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_usbnet_stats_obj, mp_usbnet_stats_py);

static const mp_rom_map_elem_t mp_usbnet_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_usbnet)},
    {MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&mp_usbnet_start_obj)},
    {MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&mp_usbnet_stop_obj)},
    {MP_ROM_QSTR(MP_QSTR_is_up), MP_ROM_PTR(&mp_usbnet_is_up_obj)},
    {MP_ROM_QSTR(MP_QSTR_ifconfig), MP_ROM_PTR(&mp_usbnet_ifconfig_obj)},
    {MP_ROM_QSTR(MP_QSTR_stats), MP_ROM_PTR(&mp_usbnet_stats_obj)},
};

static MP_DEFINE_CONST_DICT(mp_usbnet_globals, mp_usbnet_globals_table);

const mp_obj_module_t mp_module_usbnet = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&mp_usbnet_globals,
};

MP_REGISTER_MODULE(MP_QSTR_usbnet, mp_module_usbnet);
#endif // MP_USBNET_ENABLE_MICROPY_BINDINGS
