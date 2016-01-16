import os, glob, time, threading
from flask import Flask, render_template, jsonify, request, g, redirect, url_for, flash
from flask.ext.socketio import SocketIO, emit
from sqlite3 import dbapi2 as sqlite3
from pid import pidpy as PIDController
from multiprocessing import Process, Pipe, Queue, current_process
from Queue import Full
from subprocess import Popen, PIPE, call
from datetime import datetime
import time, random, serial, os
import RPi.GPIO as GPIO

os.system('modprobe w1-gpio')  # Turns on the GPIO module
os.system('modprobe w1-therm') # Turns on the Temperature module

device_file = '/sys/bus/w1/devices/28-000006281f79/w1_slave'

DATABASE = 'brewthing.db'
app = Flask(__name__)
app.config.from_object(__name__)
app.config['SECRET_KEY'] = 'Secret!'
socketio = SocketIO(app)

global current_temp, parent_conn, parent_connB, parent_connC, statusQ, statusQ_B, statusQ_C





'''----------------------------'''
''' Database methods           '''
'''----------------------------'''
def connect_db():
    return sqlite3.connect(app.config['DATABASE'])


def init_db():
    with closing(connect_db()) as db:
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

        
'''----------------------------'''
''' FLASK Routes               '''
'''----------------------------'''

@app.before_request
def before_request():
    g.db = connect_db()
    
    
@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

@app.route('/', methods=['GET'])
def main():
    start_temp_thread()
    return render_template('index.html')

@app.route('/auto', methods=['GET', 'POST'])
def automode():
    
    return render_template('auto.html')


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
    
# Thread that does timing.
class TimerThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)


    def run(self):
        while True:
            socketio.emit('current_timer_value', {'data': 'Timer', 'remaining_time': self.get_timer_update()},namespace='/events')
            time.sleep(1)

    def get_timer_update(self):
        if timer_started == True:
            remaining_time = calculate_remaining_time()

            if remaining_time > 0:
                minute, second = divmod(remaining_time, 60)
                hour, minute = divmod(minute, 60)

                time= str(hour) + ":" + str(minute) + ":" + str(second)
                                                                                                                                                                                                                                                                                                                                                                                                                                        
                return time
            else:
                global timer_started                                                        
                timer_started = False

        return "00:00:00"

    
def start_timer_thread():
    timer_thread = TimerThread()
    timer_thread.daemon = True
    timer_thread.start()
    
    

#####################
# Time helpers
#####################

# this gets the unix time in seconds.
def get_time():
    return datetime.now()


def calculate_remaining_time():
    time_to_end = start_time + end_time
    current_time = datetime.now()
    time_left = time_to_end - current_time

    return time_left.seconds

    
    
''' ----------------------'''
''' PID Processess '''
''' ----------------------'''


class param:
    status = {
        "mode" : "Auto",
        "temp" : "65",
        "tempUnits" : "C",
        "elapsed" : "0",
        "cycle_time" : 2.0,
        "duty_cycle" : 0.0,
        "boil_duty_cycle" : 60,
        "set_point" : 68.0,
        "boil_manage_temp" : 200,
        "num_pnts_smooth" : 5,
        "k_param" : 44,
        "i_param" : 165,
        "d_param" : 4             
    }
    
    
def unPackParam(paramStatus):
    mode = paramStatus["mode"]
    cycle_time = paramStatus["cycle_time"]
    duty_cycle = paramStatus["duty_cycle"]
    boil_duty_cycle = paramStatus["boil_duty_cycle"] 
    set_point = paramStatus["set_point"] 
    boil_manage_temp = paramStatus["boil_manage_temp"]
    num_pnts_smooth = paramStatus["num_pnts_smooth"]
    k_param = paramStatus["k_param"]
    i_param = paramStatus["i_param"] 
    d_param = paramStatus["d_param"] 
    
    return mode, cycle_time, duty_cycle, boil_duty_cycle, set_point, boil_manage_temp, num_pnts_smooth, \
           k_param, i_param, d_param
    
         
def gettempProc(conn, a):
    p = current_process()
    print 'Starting:', p.name, p.pid
    
    while(True):
        t = time.time()
        time.sleep(.5)
        
        #read the temperature
        num = read_temp()
        elapsed = "%.2f" % (time.time() - t)
        conn.send([num, elapsed])

        
#Get time heating element is on and off during a set cycle time
def getonofftime(cycle_time, duty_cycle):
    duty = duty_cycle/100.0
    on_time = cycle_time*(duty)
    off_time = cycle_time*(1.0-duty)   
    return [on_time, off_time]


# Stand Alone Heat Process using GPIO
def heatProcGPIO(cycle_time, duty_cycle, pinNum, conn):
    p = current_process()
    print 'Starting:', p.name, p.pid
    if pinNum > 0:
        GPIO.setup(pinNum, GPIO.OUT)
        while (True):
            while (conn.poll()): #get last
                print "in while: conn.poll()"
                cycle_time, duty_cycle = conn.recv()
            conn.send([cycle_time, duty_cycle])  
            if duty_cycle == 0:
                GPIO.output(pinNum, OFF)
                print "+ HEAT ON"
                time.sleep(cycle_time)
            elif duty_cycle == 100:
                GPIO.output(pinNum, ON)
                print "- HEAT OFF"
                time.sleep(cycle_time)
            else:
                on_time, off_time = getonofftime(cycle_time, duty_cycle)
                GPIO.output(pinNum, ON)
                print "- HEAT OFF"
                time.sleep(on_time)
                
                GPIO.output(pinNum, OFF)
                print "+ HEAT ON"
                time.sleep(off_time)
                

def heatProcGPIO2(cycle_time, duty_cycle, pinNum, conn) :
    p = current_process()
    print 'Starting:', p.name, p.pid
    
    while (True):
        while (conn.poll()):
            print "in while: conn.poll()"
            cycle_time, duty_cycle = conn.recv()
            conn.send([cycle_time, duty_cycle])  
            if duty_cycle == 0:
                #GPIO.output(pinNum, OFF)
                print "+ HEAT ON"
                time.sleep(cycle_time)
            elif duty_cycle == 100:
                #GPIO.output(pinNum, ON)
                print "+ HEAT ON"
                time.sleep(cycle_time)
            else:
                on_time, off_time = getonofftime(cycle_time, duty_cycle)
                #GPIO.output(pinNum, ON)
                print "+ HEAT ON"
                time.sleep(on_time)
                #GPIO.output(pinNum, OFF)
                print "+ HEAT ON"
                time.sleep(off_time)
    

def tempControlProc(statusQ, pinNum, conn):
    mode, cycle_time, duty_cycle, boil_duty_cycle, set_point, boil_manage_temp, num_pnts_smooth, \
        k_param, i_param, d_param = unPackParam(param.status);
        
    p = current_process()
    print "Starting", p.name, p.pid
    
    # Connections and Pipes for getting the temperature
    parent_conn_temp, child_conn_temp = Pipe()
    ptemp = Process(name = "gettempProc", target=gettempProc, args=(child_conn_temp, 0))
    ptemp.daemon = True
    ptemp.start()
    
    # Connections and Pipes for the heading
    parent_conn_heat, child_conn_heat = Pipe()      
   
    print "Pin Number is:", pinNum
    print "cycle_time", cycle_time
    print "duty_cycle", duty_cycle
    
    pheat = Process(name = "heatProcGPIO", target=heatProcGPIO, args=(cycle_time, duty_cycle, pinNum, child_conn_heat))
    pheat.daemon = True
    pheat.start()
    
    
    temp_ma_list = []
    manage_boil_trigger = False
    readyPIDcalc = False
    
    while (True):
            readytemp = False
            while parent_conn_temp.poll():
                temp_C, elapsed = parent_conn_temp.recv()
                
                if temp_C == -99:
                    print "Bad Temp Reading - retry"
                    continue
                
                temp_str = "%3.2f" % temp_C
                
                readytemp = True
                
            if readytemp:
                print "in ready temp, mode is: ", mode
                if mode == "Auto":
                    print "in auto mode----****"
                    temp_ma_list.append(temp_C)

                    #smooth data
                    temp_ma = 0.0 #moving avg init
                    while (len(temp_ma_list) > num_pnts_smooth):
                        temp_ma_list.pop(0) #remove oldest elements in list

                    if (len(temp_ma_list) < num_pnts_smooth):
                        for temp_pnt in temp_ma_list:
                            temp_ma += temp_pnt
                        temp_ma /= len(temp_ma_list)

                    else: #len(temp_ma_list) == num_pnts_smooth
                        for temp_idx in range(num_pnts_smooth):
                            temp_ma += temp_ma_list[temp_idx]
                        temp_ma /= num_pnts_smooth

                    print "Check if readyPIDcalc is set to true: ", readyPIDcalc
                    
                    #calculate PID every cycle
                    if (readyPIDcalc == True):
                        print "Calculating the PID Cycle"
                        print " -- temp_ma", temp_ma
                        print " -- set_point", set_point
                        pid = PIDController.pidpy(cycle_time, k_param, i_param, d_param) #init pid
                        duty_cycle = pid.calcPID_reg4(temp_ma, set_point, True)
                        #send to heat process every cycle
                        parent_conn_heat.send([cycle_time, duty_cycle])
                        readyPIDcalc = False
                        print "set readyPIDCalc = False"

                if mode == "boil":
                    if (temp_C > boil_manage_temp) and (manage_boil_trigger == True): #do once
                        manage_boil_trigger = False
                        duty_cycle = boil_duty_cycle
                        parent_conn_heat.send([cycle_time, duty_cycle])


                print "Current Temp: %3.2f deg %s, Heat Output: %3.1f%%" % (temp_C, "C", duty_cycle)

                readytemp == False

                #if only reading temperature (no temp control)
                if readOnly:
                    continue
                
            while parent_conn_heat.poll(): #Poll Heat Process Pipe
                cycle_time, duty_cycle = parent_conn_heat.recv() #non blocking receive from Heat Process
                readyPIDcalc = True
                print "set readyPIDCalc = True"
            
            readyPOST = False
            while conn.poll(): #POST settings - Received POST from web browser or Android device
                paramStatus = conn.recv()
                mode, cycle_time, duty_cycle_temp, boil_duty_cycle, set_point, boil_manage_temp, num_pnts_smooth, \
                    k_param, i_param, d_param = unPackParam(paramStatus)
                readyPost = True

            if readyPOST == True:
                if mode == "Auto":
                    print "Auto selected"
                    pid = PIDController.pidpy(cycle_time, k_param, i_param, d_param) #init pid
                    duty_cycle = pid.calcPID_reg4(temp_ma, set_point, True)
                    parent_conn_heat.send([cycle_time, duty_cycle])

                if mode == "Boil":
                    print "Boil selected"
                    boil_duty_cycle = duty_cycle_temp
                    duty_cycle = 100 #full power to boil manage temperature
                    manage_boil_trigger = True
                    parent_conn_heat.send([cycle_time, duty_cycle])

                if mode == "manual":
                    print "manual selected"
                    duty_cycle = duty_cycle_temp
                    parent_conn_heat.send([cycle_time, duty_cycle])
                if mode == "off":
                    print "off selected"
                    duty_cycle = 0
                    parent_conn_heat.send([cycle_time, duty_cycle])
                readyPOST = False
            time.sleep(.01)
            
            


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
    
    start_temp_thread()
    start_timer_thread()
    
    GPIO.setmode(GPIO.BCM)
    ON = 0
    OFF = 1
    readOnly = False
    current_temp = 10
    pinNum = 17
    statusQ = Queue(2)
    parent_conn, child_conn = Pipe() 
    
    p = Process(name = "TemperatureControlProcess", target=tempControlProc, args=(statusQ, pinNum, child_conn))
    p.start()
    
    socketio.run(app, host='0.0.0.0')