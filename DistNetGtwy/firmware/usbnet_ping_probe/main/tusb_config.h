#ifndef _TUSB_CONFIG_H_
#define _TUSB_CONFIG_H_

#ifdef __cplusplus
extern "C" {
#endif

#include "sdkconfig.h"

#ifndef CFG_TUSB_MCU
#define CFG_TUSB_MCU OPT_MCU_ESP32S3
#endif

#ifndef CFG_TUSB_OS
#define CFG_TUSB_OS OPT_OS_FREERTOS
#endif

#ifndef CFG_TUSB_DEBUG
#define CFG_TUSB_DEBUG 0
#endif

#ifndef CFG_TUSB_MEM_SECTION
#define CFG_TUSB_MEM_SECTION
#endif

#ifndef CFG_TUSB_MEM_ALIGN
#define CFG_TUSB_MEM_ALIGN __attribute__((aligned(4)))
#endif

#define CFG_TUSB_RHPORT0_MODE   (OPT_MODE_DEVICE | OPT_MODE_FULL_SPEED)
#define CFG_TUD_ENABLED         1
#define CFG_TUH_ENABLED         0
#define CFG_TUD_MAX_SPEED       OPT_MODE_FULL_SPEED

#ifndef CFG_TUD_ENDPOINT0_SIZE
#define CFG_TUD_ENDPOINT0_SIZE  64
#endif

// Keep this probe focused on one USB NIC class.
#define CFG_TUD_CDC             0
#define CFG_TUD_MSC             0
#define CFG_TUD_HID             0
#define CFG_TUD_MIDI            0
#define CFG_TUD_VENDOR          0
#define CFG_TUD_AUDIO           0
#define CFG_TUD_DFU             0
#define CFG_TUD_DFU_RUNTIME     0

#define CFG_TUD_ECM_RNDIS       1
#define CFG_TUD_NCM             0

#ifndef CFG_TUD_NET_MTU
#define CFG_TUD_NET_MTU         1514
#endif

#ifdef __cplusplus
}
#endif

#endif // _TUSB_CONFIG_H_

