import machine
import sys
import time

import i2c_device
import uart_device

def lfsr_taps(val: int, taps: int, bit_len: int = 32):
    bit = 0
    temp = val
    for i in range(bit_len):
        bit = bit ^ (temp & 0x01)
        temp >>= 1
        '''
        #xor output with bit at tap if tap exists
        if (taps >> i) & 0x01 == 0x01:
            bit ^= (val >> i)
        '''
        
    return bit & 0x01

def parity(val: int, bit_len: int = 32):
    '''
    Calculate the parity of a given integer
    return 1 if the number of bits is odd
    return 0 if the number of bits is even
    '''
    
    bit_sum = 0
    for i in range(bit_len):
        bit_sum += (val >> i) & 0x01
        
    return bit_sum % 2

def bit_reverse(val: int, bit_len: int = 8):
    '''
    Reverse the bits in a given int
    '''
    val_rev = 0
    
    for i in range(bit_len):
        val_rev |= ((val >> i) & 0x01) << (bit_len - 1 - i)

    return val_rev

def wspr_int(char):
    c = ord(char)
    
    if 48 <= c <= 57:
        return c - 48
    elif c == 32:
        return 36
    else:
        return c - 65 + 10

def generate_wspr_message(callsign: str, grid: str, power: int):
    #28 bits callsign
    #15 bits locator
    #7 bits power level
    
    valid_powers = (0, 3, 7)
    
    assert power % 10 in valid_powers
    assert 0 <= power <= 60

    #third character must be a digit, prepend spaces if not
    while not callsign[2].isdigit():
        callsign = " " + callsign
      
    #callsigns must be 6 chars, pad if not
    while len(callsign) != 6:
        callsign += " "
        
    #squash callsign into 28 bit integer
    call_int = 0
    for i, c in enumerate(callsign):
        if i == 0:
            call_int = wspr_int(c)
        elif i == 1:
            call_int = call_int * 36 + wspr_int(c)
        elif i == 2:
            call_int = call_int * 10 + wspr_int(c)
        else:
            call_int = 27 * call_int + wspr_int(c) - 10
    
    #squash grid square into 15 bit integer
    grid_int = int((179 - 10 * (ord(grid[0]) - 65) - int(grid[2])) * 180 + 10 * (ord(grid[1]) - 65) + int(grid[3]))
    
    #encode power and add it to grid square int
    pwr_int = grid_int * 128 + power + 64
    
    #combine into 50 bit int
    comb_int = ((call_int << 22) | (pwr_int & 0x3FFFFF)) << 6
    
    #pack comb_int into c_array
    c_array = [0] * 11
    for i in range(7):
        c_array[i] = (comb_int >> 8 * (6 - i)) & 0xFF
    
    '''
    for byte in c_array: #verified this is correct
        print(hex(byte), end=' ')
    print()
    '''
    
    #apply FEC encoding
    R_0 = 0 #shift registers
    R_1 = 0
    FEC_array = []
    
    for i in range(81):
        #shift to make room for next bit
        R_0 <<= 1
        R_1 <<= 1
        
        #shift in MSB
        int_bit = (c_array[int(i / 8)] >> (7 - (i % 8))) & 0x01
        
        #populate shift registers
        R_0 |= int_bit
        R_1 |= int_bit

        #AND with magic numbers and calculate parity
        R_0_parity = parity(R_0 & 0xF2D05351)
        R_1_parity = parity(R_1 & 0xE4613C47)

        #push to bit array
        FEC_array.append(R_0_parity)
        FEC_array.append(R_1_parity)

    #interleave bits
    d_array = [0] * 162
    i = 0
    for j in range(255):
        r = bit_reverse(j)
        
        if (r < 162):
            d_array[r] = FEC_array[i]
            i += 1
            
        if (i >= 162):
            break

    #merge with sync vector (162 bits)
    sync = [1,1,0,0,0,0,0,0,1,0,0,0,1,1,1,0,0,0,1,0,0,1,0,1,1,1,1,0,0,0,0,0,0,0,1,0,0,1,0,1,0,0,
            0,0,0,0,1,0,1,1,0,0,1,1,0,1,0,0,0,1,1,0,1,0,0,0,0,1,1,0,1,0,1,0,1,0,1,0,0,1,0,0,1,0,
            1,1,0,0,0,1,1,0,1,0,1,0,0,0,1,0,0,0,0,0,1,0,0,1,0,0,1,1,1,0,1,1,0,0,1,1,0,1,0,0,0,1,
            1,1,0,0,0,0,0,1,0,1,0,0,1,1,0,0,0,0,0,0,0,1,1,0,1,0,1,1,0,0,0,1,1,0,0,0]

    output = [0] * 162
    for i in range(162):
        output[i] = sync[i] + 2 * d_array[i]
        
    return output

i2c = machine.I2C(1, scl=machine.Pin(27), sda=machine.Pin(26),
                  freq=100000, timeout=500000)
clockgen = i2c_device.SI5351(i2c)

uart0 = machine.UART(0, baudrate=9600, tx=machine.Pin(16), rx=machine.Pin(17), timeout=100)
gps = uart_device.TEL0132(uart0)

#clockgen programming
#20m WSPR from 14.0970 - 14.0972 MHz (200 Hz bandwidth)
#4x tones with 1.465 Hz Spacing
#for output purity, should adjust VCO divider before adjusting output divider
#disable clocks
clockgen.enable_output(0, False)
clockgen.enable_output(1, False)
clockgen.enable_output(2, False)

clockgen.configure_output_driver(1)
clockgen.enable_output(1, True)

#28 + (195364 / 1000000) = 14.097.000 MHz
#375/256 tone spacing = 1.465 Hz
#1.465 Hz / 3 = 0.4883333...
#therefore offset 256 * 3 = 768 should equal base + 375
clockgen.transmit_wspr_tone(1, "20m", 0, correction=0)
clockgen.reset_plls()

print("=======")
#generate_wspr_message("W6NXP", "AA00", 13)
print()
print(generate_wspr_message("W6NXP", "DM03", 13))
print('\n')