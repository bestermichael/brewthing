import os, glob, time, threading
from flask import Flask, render_template, jsonify, request, g, redirect, url_for, flash
from flask.ext.socketio import SocketIO, emit

os.system('modprobe w1-gpio')  # Turns on the GPIO module
os.system('modprobe w1-therm') # Turns on the Temperature module

device_file = '/sys/bus/w1/devices/28-000006281f79/w1_slave'

app = Flask(__name__)
app.config.from_object(__name__)
app.config['SECRET_KEY'] = 'Secret!'
socketio = SocketIO(app)




@app.route('/', methods=['GET'])
def main():
    start_temp_thread()
    return render_template('index.html')


@socketio.on('connect_event', namespace='/events')
def test_message(message):
    print "A Client Connected"
    
    
'''----------------------------'''
''' THREADS and THREAD METHODS '''
'''----------------------------'''



def start_temp_thread():
    temp_thread = TempThread()
    temp_thread.daemon = True
    temp_thread.start()



# Thread to continiously read and update temperature
class TempThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)


    def run(self):
        while True:
            print 'Sending Temperature: ' + str(self.get_temp_update())
            socketio.emit('current_temperature', {'data':'Temperature','current_temp': self.get_temp_update()}, namespace='/events')
            time.sleep(1)
            
            
    def get_temp_update(self):
        # Read temperature from the Pi
        return read_temp()






'''------------------------'''
''' MOVE TO MODULES FOLDER '''
'''------------------------'''

# A function that reads the sensors data
def read_temp_raw():
    f = open(device_file, 'r') # Opens the temperature device file
    lines = f.readlines() # Returns the text
    f.close()
    return lines
 
# Convert the value of the sensor into a temperature

def read_temp():
    lines = read_temp_raw() # Read the temperature 'device file'
 
    # While the first line does not contain 'YES', wait for 0.2s
    # and then read the device file again.
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw()

    # Look for the position of the '=' in the second line of the
    # device file.
    equals_pos = lines[1].find('t=')

    # If the '=' is found, convert the rest of the line after the
    # '=' into degrees Celsius, then degrees Fahrenheit
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
    return temp_c   


    
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0')