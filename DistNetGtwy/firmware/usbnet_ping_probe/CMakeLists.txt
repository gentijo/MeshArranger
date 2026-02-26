cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../components/mp_usbnet_plugin"
    "${CMAKE_CURRENT_LIST_DIR}/../../micropython/ports/esp32/managed_components/espressif__tinyusb"
)

# TinyUSB sources include "tusb_config.h"; keep the probe's config globally visible.
add_compile_options(-I${CMAKE_CURRENT_LIST_DIR}/main)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(usbnet_ping_probe)

