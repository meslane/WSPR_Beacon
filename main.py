import machine
import sys
import time

import i2c_device
import uart_device
import wspr

i2c = machine.I2C(1, scl=machine.Pin(27), sda=machine.Pin(26),
                  freq=100000, timeout=500000)
uart0 = machine.UART(0, baudrate=9600, tx=machine.Pin(16), rx=machine.Pin(17), timeout=100)


beacon = wspr.Beacon(i2c, uart0)

beacon.tone_spacing = 10000
beacon.generate_message("W6NXP", "DM03", 13)
beacon.configure_clockgen("20m", 100)

beacon.transmit_message()