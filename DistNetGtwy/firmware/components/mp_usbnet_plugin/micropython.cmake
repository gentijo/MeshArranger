# MicroPython USER_C_MODULES entry for the usbnet module.
add_library(usermod_mp_usbnet_plugin INTERFACE)

target_sources(usermod_mp_usbnet_plugin INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/mp_usbnet.c
    ${CMAKE_CURRENT_LIST_DIR}/usb_netif_glue.c
    ${CMAKE_CURRENT_LIST_DIR}/usb_netif_port.c
)

target_include_directories(usermod_mp_usbnet_plugin INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/include
)

target_link_libraries(usermod INTERFACE usermod_mp_usbnet_plugin)
