== CALIBRATION ==

The 25 MHz crystals used on the Adafruit breakout boards are not
particuarly accurate, and calibration with a frequency counter may be
needed to ensure that the output tone matches the programmed frequency.


== WARMUP ==

The Si5351 has ~10-20 Hz of measured drift across temperature from 
startup to steady state. It is reccomended to let the oscillator 
warm up for approximately 30 minutes to ensure transmission accuracy.