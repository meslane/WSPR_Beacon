import machine
import sys
import time

import i2c_device
import uart_device

i2c = machine.I2C(1, scl=machine.Pin(27), sda=machine.Pin(26),
                  freq=100000, timeout=500000)
clockgen = i2c_device.SI5351(i2c)

uart0 = machine.UART(0, baudrate=9600, tx=machine.Pin(16), rx=machine.Pin(17), timeout=100)
gps = uart_device.TEL0132(uart0)

clockgen.i2c_write(0x03, 0xff)

#clockgen programming

#disable clocks
clockgen.enable_output(0, False)
clockgen.enable_output(1, False)
clockgen.enable_output(2, False)

clockgen.load_register_map("14m_reg_map.txt")

clockgen.reset_plls()

#enable output 1
clockgen.enable_output(1, True)

print('\n')
clockgen.register_dump(stop=255)