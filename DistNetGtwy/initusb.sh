#!/bin/sh
nmcli device set usb0 managed no
sudo ip link set usb0 up
sudo ip addr flush dev usb0
sudo ip addr add 192.168.137.1/24 dev usb0
sudo ip neigh flush dev usb0
sudo arping -I usb0 -c 5 192.168.137.2
ping -I usb0 -c 5 192.168.137.2
ip -s link show dev usb0

