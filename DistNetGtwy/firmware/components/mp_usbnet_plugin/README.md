# mp_usbnet_plugin

ESP-IDF 5.5 component intended for MicroPython ESP32-S3 firmware builds.

## What it provides

- MicroPython module: `usbnet`
- API:
  - `usbnet.start(hostname, ip, netmask, gateway)`
  - `usbnet.stop()`
  - `usbnet.is_up()`
- Creates an `esp_netif` object and applies static IPv4 config.
- Hook point for TinyUSB USB-NIC to lwIP packet bridge in `usb_netif_glue.c`.

## Status

- Module registration and control path are implemented.
- TinyUSB network integration is implemented via:
  - `esp_tinyusb` (`tinyusb_net_init`) when available, or
  - direct TinyUSB net callbacks (`tud_network_*`) in MicroPython builds.
- USB RX frames are fed into lwIP via `esp_netif_receive()`, and lwIP TX is sent to USB via `tinyusb_net_send_sync()` or `tud_network_xmit()` (backend-dependent).

## Integration notes

1. Add this component to your ESP-IDF project components path.
2. Ensure MicroPython external module headers are visible in component include paths.
3. Ensure TinyUSB net class is enabled in firmware TinyUSB config (`CFG_TUD_ECM_RNDIS` or `CFG_TUD_NCM`).
4. Select plugin class in Kconfig (`MP_USBNET_USB_CLASS_ECM` or `MP_USBNET_USB_CLASS_RNDIS`).
   - If component Kconfig is not visible in your build path, it defaults to ECM.
5. In your MicroPython startup script, call:

```python
import usbnet
usbnet.start("mesh-gateway", "192.168.137.2", "255.255.255.0", "192.168.137.1")
```

6. Start mDNS in firmware (or MicroPython layer) with hostname `mesh-gateway.local`.

## Notes

- `MP_USBNET_USB_CLASS_*` selects expected class in this plugin.
- Actual USB class exposure comes from TinyUSB descriptor/config (`shared/tinyusb/tusb_config.h` in MicroPython builds).
