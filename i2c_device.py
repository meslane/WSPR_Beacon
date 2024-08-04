import machine

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
        
    def load_register_map(self, filename):
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
                