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

#clockgen programming
#20m WSPR from 14.0970 - 14.0972 MHz
#for output purity, should adjust VCO divider before adjusting output divider
#disable clocks
clockgen.enable_output(0, False)
clockgen.enable_output(1, False)
clockgen.enable_output(2, False)

clockgen.configure_output_driver(1)

pll_a = 28
pll_b = 0
pll_c = 500

synth_a = 50
synth_b = 0
synth_c = 1

clockgen.configure_pll(0, pll_a, pll_b, pll_c) #PPL A fVCO = 28 + 1/5
clockgen.configure_output_multisynth(1, synth_a, synth_b, synth_c) #output divider = 50

print(clockgen.calculate_frequency(pll_a, pll_b, pll_c, synth_a, synth_b, synth_c))

clockgen.reset_plls()

#enable output 1
clockgen.enable_output(1, True)

print('\n')
#clockgen.register_dump(stop=255)