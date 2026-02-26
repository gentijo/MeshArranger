#include <string.h>

#include "esp_mac.h"
#include "tusb.h"

// Shared with TinyUSB NET class and the usbnet plugin backend.
extern uint8_t tud_network_mac_address[6];

enum {
    STRID_LANGID = 0,
    STRID_MANUFACTURER,
    STRID_PRODUCT,
    STRID_SERIAL,
    STRID_INTERFACE,
    STRID_MAC,
};

enum {
    ITF_NUM_NET = 0,
    ITF_NUM_NET_DATA,
    ITF_NUM_TOTAL,
};

#define USB_PID (0x4000 | (CFG_TUD_ECM_RNDIS << 5) | (CFG_TUD_NCM << 5))

static const tusb_desc_device_t s_desc_device = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = TUSB_CLASS_MISC,
    .bDeviceSubClass = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = 0x303A,   // Espressif
    .idProduct = USB_PID,
    .bcdDevice = 0x0100,
    .iManufacturer = STRID_MANUFACTURER,
    .iProduct = STRID_PRODUCT,
    .iSerialNumber = STRID_SERIAL,
    .bNumConfigurations = 1,
};

uint8_t const *tud_descriptor_device_cb(void) {
    return (uint8_t const *)&s_desc_device;
}

#define EPNUM_NET_NOTIF 0x81
#define EPNUM_NET_OUT   0x02
#define EPNUM_NET_IN    0x82

#if CFG_TUD_ECM_RNDIS
#define CONFIG_TOTAL_LEN (TUD_CONFIG_DESC_LEN + TUD_CDC_ECM_DESC_LEN)
static const uint8_t s_desc_configuration[] = {
    TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, 0, CONFIG_TOTAL_LEN, 0, 100),
    TUD_CDC_ECM_DESCRIPTOR(ITF_NUM_NET,
                           STRID_INTERFACE,
                           STRID_MAC,
                           EPNUM_NET_NOTIF,
                           64,
                           EPNUM_NET_OUT,
                           EPNUM_NET_IN,
                           CFG_TUD_NET_ENDPOINT_SIZE,
                           CFG_TUD_NET_MTU),
};
#else
#define CONFIG_TOTAL_LEN (TUD_CONFIG_DESC_LEN + TUD_CDC_NCM_DESC_LEN)
static const uint8_t s_desc_configuration[] = {
    TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, 0, CONFIG_TOTAL_LEN, 0, 100),
    TUD_CDC_NCM_DESCRIPTOR(ITF_NUM_NET,
                           STRID_INTERFACE,
                           STRID_MAC,
                           EPNUM_NET_NOTIF,
                           64,
                           EPNUM_NET_OUT,
                           EPNUM_NET_IN,
                           CFG_TUD_NET_ENDPOINT_SIZE,
                           CFG_TUD_NET_MTU),
};
#endif

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
    (void)index;
    return s_desc_configuration;
}

static const char *const s_string_desc_arr[] = {
    (const char[]){0x09, 0x04}, // 0: English
    "Espressif Systems",        // 1: Manufacturer
    "USBNET Ping Probe",        // 2: Product
    NULL,                       // 3: Serial from base MAC
    "USB Network Interface",    // 4: Interface
};

static uint16_t s_desc_str[33];

static size_t fill_hex_ascii(char *out, size_t out_len, const uint8_t *src, size_t src_len) {
    static const char *hex = "0123456789ABCDEF";
    size_t n = 0;
    for (size_t i = 0; i < src_len && (n + 2) < out_len; ++i) {
        out[n++] = hex[(src[i] >> 4) & 0x0F];
        out[n++] = hex[src[i] & 0x0F];
    }
    out[n] = '\0';
    return n;
}

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    (void)langid;

    size_t chr_count = 0;
    if (index == STRID_LANGID) {
        memcpy(&s_desc_str[1], s_string_desc_arr[0], 2);
        chr_count = 1;
    } else if (index == STRID_SERIAL) {
        uint8_t mac[6] = {0};
        esp_efuse_mac_get_default(mac);
        char serial[32];
        chr_count = fill_hex_ascii(serial, sizeof(serial), mac, sizeof(mac));
        for (size_t i = 0; i < chr_count; ++i) {
            s_desc_str[1 + i] = serial[i];
        }
    } else if (index == STRID_MAC) {
        char mac_str[32];
        chr_count = fill_hex_ascii(mac_str, sizeof(mac_str),
                                   tud_network_mac_address,
                                   sizeof(tud_network_mac_address));
        for (size_t i = 0; i < chr_count; ++i) {
            s_desc_str[1 + i] = mac_str[i];
        }
    } else {
        if (index >= sizeof(s_string_desc_arr) / sizeof(s_string_desc_arr[0])) {
            return NULL;
        }
        const char *str = s_string_desc_arr[index];
        if (str == NULL) {
            return NULL;
        }
        chr_count = strlen(str);
        if (chr_count > 32) {
            chr_count = 32;
        }
        for (size_t i = 0; i < chr_count; ++i) {
            s_desc_str[1 + i] = str[i];
        }
    }

    s_desc_str[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * chr_count + 2));
    return s_desc_str;
}

