import machine
import sys
import time
import random

import i2c_device
import uart_device

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
    '''
    Convert a char to an int the way WSPR wants it
    '''
    
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


class Beacon:
    def __init__(self, i2c: machine.I2C, uart: machine.UART, pps: machine.Pin):
        #constants
        self.tone_period = 683 #ms
        self.tone_spacing = 1.465 #Hz
        self.message_length = 162 #tones
        
        self.clockgen = i2c_device.SI5351(i2c)
        self.gps = uart_device.TEL0132(uart)
        self.timer = machine.Timer(period=self.tone_period, mode = machine.Timer.PERIODIC,
                   callback=None)
        self.timer.deinit()
        
        #GPS PPS output
        self.pps = pps
        self.pps_count = 0
        self.last_pps = 0
        pps.irq(trigger=machine.Pin.IRQ_RISING, handler=self.pps_interrupt)
        
        self.led = machine.Pin(25, machine.Pin.OUT)
        self.led.off()
        
        self.tone_index = 0
        self.message = []
        
        self.band = None
        self.offsets = None
        self.offset_index = 0
        self.output = None
        
        self.state = "init"
    
    def generate_message(self, callsign: str, grid: str, power: str):
        self.message = generate_wspr_message(callsign, grid, power)
    
    def configure_clockgen(self, band: str, offsets: tuple[int], output: int = 1):
        '''
        Set transmit freq and get frontend ready
        '''
        self.band = band
        self.offsets = offsets
        self.output = output
        
        self.clockgen.configure_output_driver(self.output)
        self.clockgen.enable_output(self.output, False)
        
    def transmit_next_tone(self, *args):
        '''    
        Transmit the next tone in the message buffer
        This should be called from a clock interrupt, not directly
        '''
        #make sure we got one in the chamber
        assert len(self.message) == self.message_length
        assert self.band != None
        assert self.offsets != None
        assert self.output != None
        
        if self.tone_index >= 162:
            self.clockgen.enable_output(self.output, False)
            self.timer.deinit() #message is finished, stop timer
            self.tone_index = 163
        else:
            if self.tone_index == 0:
                self.clockgen.enable_output(self.output, True)
            
            if isinstance(self.offsets, int):
                tone_offset = self.offsets + (self.message[self.tone_index] * self.tone_spacing)
            else:
                tone_offset = self.offsets[self.offset_index] + (self.message[self.tone_index] * self.tone_spacing)
            
            self.tone_index += 1
            self.clockgen.transmit_wspr_tone(self.output, self.band,
                                             tone_offset, correction=0)
        
    def transmit_message(self):
        '''
        start timer and begin transmitting
        '''
        self.timer.init(period = self.tone_period,
                        mode = machine.Timer.PERIODIC,
                        callback = self.transmit_next_tone)
    
    def pps_interrupt(self, *args):
        self.led.toggle()
        self.pps_count += 1
    
    def run(self):
        start_state = self.state
        
        #state machine
        if self.state == "init":
            self.state = "no_fix"
            
        elif self.state == "no_fix":
            if self.pps_count != self.last_pps:
                self.state = "wait_for_transmit"
                
        elif self.state == "wait_for_transmit":
            gps_time = self.gps.get_time_and_position()[0]
            
            if gps_time == "N/A":
                self.state = "no_fix"
            else: #if have a fix
                #trigger on rising PPS pulse to transmit at the start of the minute
                if int(gps_time[4]) % 2 == 1 and int(gps_time[6:8]) == 59:
                    #pick next offset
                    if isinstance(self.offsets, int):
                        self.offset_index = 0
                        print("Offset = {}".format(self.offsets))
                    else:
                        self.offset_index = random.randint(0, len(self.offsets)) #pick new random offset from list
                        print("Offset = {}".format(self.offsets[self.offset_index]))
                    
                    self.state = "await_pps"
                    
        elif self.state == "await_pps":
            if self.pps_count != self.last_pps:
                self.transmit_message() #begin transmission
                self.state = "transmit"

        elif self.state == "transmit":
            if self.tone_index == 163:
                self.tone_index = 0
                self.state = "wait_for_transmit"
                
        self.last_pps = self.pps_count
        
        if self.state != start_state:
            print("{} - {}".format(self.state, self.pps_count))
        
        time.sleep(0.01)