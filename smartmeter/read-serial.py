#!/usr/bin/env python3
import serial
from time import sleep


try:
    output = open("smartmeter-data.raw", "wb")

    # serial port ttyS0 or ttyAMA0
    # we use just serial1 -> ttyAMA0
    ser = serial.Serial("/dev/ttyUSB0", 9600)  # Open port with baud rate
    while True:
        received_data = ser.read()  # read serial port
        sleep(0.03)
        data_left = ser.inWaiting()  # check for remaining byte
        received_data += ser.read(data_left)
        print(received_data)

        output.write(received_data)
        output.flush()
        # ser.write(received_data)                #transmit data serially

finally:
    output.close()
    ser.close()
