import machine

class UART_Device:
    def __init__(self, uart: machine.UART):
        self.uart = uart
        
class TEL0132(UART_Device):
    def __init__(self, uart: machine.UART):
        super().__init__(uart)
        
    def get_time_and_position(self):
        '''
        Flush the UART buffer if full and grab the most recent UTC timestamp and coords from GPS
        
        Returns:
            (time, (lat, lon))
        '''
        if self.uart.any() > 0:
            self.uart.flush()
        
        while True:
            #wait for UART buffer to be full
            while self.uart.any() == 0:
                pass
            
            try:
                uart_str = self.uart.readline().decode("utf-8")
            except UnicodeError:
                uart_str = "000000"
            
            #exit once we get the right string
            if uart_str[0:6] == '$GNGGA':
                break

        gps_time = uart_str[7:9] + ':' + uart_str[9:11] + ':' + uart_str[11:13]
        gps_lat = int(uart_str[18:20]) + (float(uart_str[20:28]) / 60)
        gps_lon = int(uart_str[31:34]) + (float(uart_str[34:42]) / 60)

        #if south or west, make negative
        if uart_str[29] == 'S':
            gps_lat *= -1
        if uart_str[43] == 'W':
            gps_lon *= -1

        return (gps_time, (gps_lat, gps_lon))