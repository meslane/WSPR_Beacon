import machine
import math

class I2C_Device:
    def __init__(self, i2c: machine.I2C, address: int, addrsize: int = 8):
        self.i2c = i2c
        self.address = address
        self.addrsize = addrsize
        
    def i2c_write(self, register: int, data):
        #I2C write will fail if you just pass a bytearray constructed from the data
        buffer = bytearray(1)
        buffer[0] = 0xFF & data
        
        self.i2c.writeto_mem(self.address, register, buffer, addrsize=self.addrsize)
        
    def i2c_read(self, register: int, len_data = 1):
        assert len_data >= 1
        i2c_bytes = self.i2c.readfrom_mem(self.address, register, len_data, addrsize=self.addrsize)
        return int.from_bytes(i2c_bytes, "big")
    
    def register_dump(self, start=0, stop=256):
        for i in range(start, stop):
            data = self.i2c_read(i)
            
            print("{:03d} - 0x{:02x}: ".format(i, i), end='')
            
            if data == 0:
                print('-')
            else:
                print("0x{:02x}".format(data))
                
class SI5351(I2C_Device):
    def __init__(self, i2c: machine.I2C, address: int = 0x60):
        super().__init__(i2c, address)
        
    def enable_output(self, clk_channel: int, output: bool):
        '''
        Turn the desired output on or off
        '''
        channel = clk_channel + 16 #register offset
        control_data = self.i2c_read(channel) #channel shutdown control
        enable_data = self.i2c_read(0x03) #output enable control
        
        if output:
            self.i2c_write(channel, (control_data & ~0x80))
            self.i2c_write(0x03, (enable_data & ~(0x01 << clk_channel)))
        else:
            self.i2c_write(channel, (control_data | 0x80))
            self.i2c_write(0x03, (enable_data | (0x01 << clk_channel)))
    
    def configure_pll(self, pll: int, mult: int, num: int, denom: int):
        '''
        Configure PLL output multisynth
        Adapted from: https://github.com/adafruit/Adafruit_Si5351_Library/blob/master/Adafruit_SI5351.cpp
        
        fVCO is the PLL output, and must be between 600..900MHz, where:

        fVCO = fXTAL * (a+(b/c))

        fXTAL = the crystal input frequency
        a [mult]    = an integer between 15 and 90
        b [num]     = the fractional numerator (0..1,048,575)
        c [denom]   = the fractional denominator (1..1,048,575)
        '''
        #constrain to valid values
        assert 15 <= mult <= 90
        assert 0 < denom <= 0xFFFFF
        assert num <= 0xFFFFF
        
        if num == 0: #integer
            P1 = int(128 * mult - 512)
            P2 = num
            P3 = denom
        else: #fractional
            P1 = int(128 * mult + math.floor(128 * (num/denom)) - 512)
            P2 = int(128 * num - denom * math.floor(128 * (num/denom)))
            P3 = denom
        
        if pll == 0: #PLL A
            base = 26
        else: #PLL B
            base = 34
        
        #write registers
        self.i2c_write(base, (P3 >> 8) & 0xFF)
        self.i2c_write(base + 1, P3 & 0xFF)
        self.i2c_write(base + 2, (P1 & 0x00030000) >> 16)
        self.i2c_write(base + 3, (P1 >> 8) & 0xFF)
        self.i2c_write(base + 4, P1 & 0xFF)
        self.i2c_write(base + 5, ((P3 & 0x000F0000) >> 12) | ((P2 & 0x000F0000) >> 16))
        self.i2c_write(base + 6, (P2 >> 8) & 0xFF)
        self.i2c_write(base + 7, P2 & 0xFF)
    
    def configure_output_multisynth(self, channel: int, div: int, num: int, denom: int):
        '''
        Configure channel output multisynth
        Adapted from: https://github.com/adafruit/Adafruit_Si5351_Library/blob/master/Adafruit_SI5351.cpp

        fOUT = fVCO / (a + (b/c))

        a [div]   = The integer value, which must be 4, 6 or 8 in integer mode (MSx_INT=1)
                    or 8..900 in fractional mode (MSx_INT=0).
        b [num]   = The fractional numerator (0..1,048,575)
        c [denom] = The fractional denominator (1..1,048,575)
        '''
        
        assert 0 <= channel <= 2
        assert 4 <= div <= 2048
        assert 0 <= num <= 0xFFFFF
        assert 0 <= denom <= 0xFFFFF
    
        if num == 0: #integer
            P1 = int(128 * div - 512)
            P2 = 0
            P3 = denom
        else: #fractional
            P1 = int(128 * div + math.floor(128 * num / denom) - 512)
            P2 = int(128 * num - denom * math.floor(128 * num / denom))
            P3 = denom
            
        if channel == 0:
            base = 42
        elif channel == 1:
            base = 50
        else:
            base = 58
        
        #write registers
        self.i2c_write(base, (P3 >> 8) & 0xFF)
        self.i2c_write(base + 1, P3 & 0xFF)
        self.i2c_write(base + 2, (P1 & 0x00030000) >> 16)
        self.i2c_write(base + 3, (P1 >> 8) & 0xFF)
        self.i2c_write(base + 4, P1 & 0xFF)
        self.i2c_write(base + 5, ((P3 & 0x000F0000) >> 12) | ((P2 & 0x000F0000) >> 16))
        self.i2c_write(base + 6, (P2 >> 8) & 0xFF)
        self.i2c_write(base + 7, P2 & 0xFF)
    
    def configure_output_driver(self, channel: int, int_mode: int = 1, pll_source: int = 0,
                                invert: int = 0, input_source: int = 0x03, drive: int = 0x03):
        '''
        Configure the output driver for the selected output channel
        '''
        assert 0 <= channel <= 2
        channel_addr = channel + 16
        
        data = self.i2c_read(channel_addr) & 0x80 #keep enable bit
        data |= (int_mode << 6) | (pll_source << 5) | (invert << 4) | (input_source << 2) | drive
        
        self.i2c_write(channel + 16, data)
    
    def reset_plls(self):
        self.i2c_write(177, 0xA0)
        
    def set_load_capacitance(self, cl: int):
        cl_list = [6, 8, 10]
        assert cl in cl_list
        
        setting = 0xC0
        
        if cl == 6:
            setting = 0x40
        elif cl == 8:
            setting = 0x80
            
        self.i2c_write(183, setting)
        
    def load_register_map(self, filename: str):
        '''
        Load a register map file generated from ClockBuilder
        '''
        f = open(filename, 'r')
        
        lines = f.readlines()
        for line in lines:
            if line[0] != '#': #if not comment
                address = int(line[0:3])
                data = int(line[4:6], 16)
                
                if address < 200: #writing above this bricks i2c
                    self.i2c_write(address, data)
                    
    def calculate_frequency(self, pll_a, pll_b, pll_c, multi_a, multi_b, multi_c, f_vco = 25e6):
        '''
        Helper function to calculate frequency based on synth constants
        '''
        
        f_pll = float(f_vco * (pll_a + (pll_b / pll_c)))
        f_out = float(f_pll / (multi_a + (multi_b/multi_c)))
        return f_out
    
    def transmit_wspr_tone(self, channel: int, band: str,
                           offset: float, pll: int = 0, correction: int = 0):
        '''
        Transmit a WSPR tone in the given ham band with specified offset
        Assumes output is configured beforehand
        
        Args:
            channel: output channel to use (0, 1, 2)
            band: string denoting which ham band to transmit in
            offset: frequency offset from start of band (in Hz)
            pll [optional]: the pll used for the output source
            correction [optional]: frequency correction factor to account for drift
        '''  

        #200 Hz WSPR allocation on all bands
        assert 0 <= offset #<= 200
        
        if band == "20m": #base freq = 14.097.000 MHz
            pll_a = 28
            pll_b_base = 200052
            pll_c = 1023890
            output_divider = 50
        elif band == "40m": #base freq = 7.040.000 MHz
            pll_a = 28
            pll_b_base = 82619
            pll_c = 511945
            output_divider = 100
            
        #set output divider
        self.configure_output_multisynth(channel, output_divider, 0, 1)
        #magic numbers for 1.465 Hz tone spacing
        self.configure_pll(pll, pll_a, pll_b_base + int((offset + correction) * 2.04778157), pll_c)