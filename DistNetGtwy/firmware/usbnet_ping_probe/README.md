# usbnet_ping_probe

Standalone ESP-IDF ESP32-S3 probe app to validate USB CDC-ECM ping behavior
without the MicroPython runtime.

It reuses the same `mp_usbnet_plugin` backend used by the `usbnet` MicroPython
module, but drives it directly from `app_main()`.

## What it proves

- USB network class enumerates on host.
- Device static IPv4 is `192.168.137.2/24` with gateway `192.168.137.1`.
- Device receives host traffic and attempts transmit (logged via counters).

## Build

From `firmware/usbnet_ping_probe`:

```bash
idf.py set-target esp32s3
idf.py build
```

## Flash

```bash
idf.py -p /dev/ttyUSB0 flash
```

Then start a monitor only if needed for logs. If your monitor toggles RTS/DTR on
the same USB controller used for ECM, it can reset/disconnect the USB NIC.

## Host setup (Linux)

```bash
nmcli device set usb0 managed no
sudo ip link set usb0 up
sudo ip addr flush dev usb0
sudo ip addr add 192.168.137.1/24 dev usb0
sudo ip neigh flush dev usb0
sudo arping -I usb0 -c 5 192.168.137.2
ping -I usb0 -c 5 192.168.137.2
```

## Runtime logs

The app prints `ifconfig` and `stats` every 2 seconds:

- `rx_ok` / `rx_err` = host->device frame path
- `tx_ok` / `tx_err` = device->host frame path

Healthy ping behavior should increase both `rx_ok` and `tx_ok`.
