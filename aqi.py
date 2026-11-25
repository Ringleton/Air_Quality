# V8 Added stats summary to X label of graph when showing entire Jan to Dec year.
# V7 Moved Adafruit IoT parameters to a config.json file in preparation
#    to upload to github.
# V6 Major changes starting to load DB and graph multiple date ranges.
# V5 Slight print mods to detect error message in order to fix it.
# V4 Cleaned up plot major formatter.  Added quit confirmation dialog.
#    Changed foreground color to white for better contrast on darker index colors.
# V3 Now includes plot on lower half of screen
# V2 now with GUI
# Get and publish AQI reading to Adafruit IO

from tkinter import *
# Next, replace basic Tk widgets with Tk themed widgets so we can use "Styles"
from tkinter import ttk
# Allows us to create our own custom font objects
from tkinter.font import Font
from tkinter.messagebox import askokcancel, WARNING

import time
import board
import busio
from datetime import datetime, timedelta
from adafruit_pm25.i2c import PM25_I2C
from Adafruit_IO import Client
from apscheduler.schedulers.background import BackgroundScheduler

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg)

import sqlite3
import pandas as pd

import os
import json

def refresh_display(clicked_button):
    
    global graph_num, graph_year, year_setting, min_year
    
    conn = sqlite3.connect("air.db", detect_types=sqlite3.PARSE_DECLTYPES, timeout=30.0)
    cursor = conn.cursor()

    # One time only, determine minumum year in DB
    if min_year == -1:
        query = "SELECT MIN(time) FROM readings"
        cursor.execute(query)
        value = cursor.fetchone()[0]
        min_year=int(value[0:4])

    # Assumes rightmost button is for 1 year.
    year_button = len(aqi_list)-1

    if clicked_button != -1 or (clicked_button == -1 and not (graph_num == year_button and graph_year != 365)):
        end_date = datetime.now() # May get changed below
        
    if clicked_button != -1:
        graph_num = clicked_button
        
    if clicked_button == -1 and graph_year != 365:
        end_date = datetime(graph_year,12,31,23,59,59)
        
    if clicked_button == year_button:
        if year_setting == 365: # Year button show "1 Year"
            graph_year = 365
            year_setting = end_date.year
        else: # Year button had actual year in it...
            end_date = datetime(year_setting,12,31,23,59,59)
            graph_year = year_setting
            if year_setting > min_year:
                year_setting -= 1
            else:
                year_setting = 365
                
        if year_setting == 365:
            ButtonLabel[year_button].config(text=aqi_list[year_button][0])
        else:
            ButtonLabel[year_button].config(text=str(year_setting))
    
    elif clicked_button != -1:
        year_setting = 365
        graph_year = 365
        ButtonLabel[year_button].config(text=aqi_list[year_button][0])
    
    end_date_up = datetime.now()
    for i in range(len(aqi_list)):
        start_date = end_date_up - aqi_list[i][1]

        query = "SELECT AVG(pm2_5) FROM readings WHERE time BETWEEN ? AND ?"
    
        cursor.execute(query, (start_date, end_date_up))
         
        # in case no records found (no recent data)
        value = cursor.fetchone()[0]
        if value is not None:
            value = round(value)
        else:
            value = 0

        AqiNum[i].set(value)
        fg, bg = get_aqi_color(value)

        AqiStyle[i].configure('AqiStyle'+str(i)+'.TLabel', foreground=fg, background=bg)

    # Use end_date from up above
    start_date = end_date - aqi_list[graph_num][1]

    query = "SELECT time, pm2_5 FROM readings WHERE time BETWEEN ? AND ?"
    
    cursor.execute(query, (start_date, end_date))

    rows = cursor.fetchall()
    x = [row[0] for row in rows]
    y = [row[1] for row in rows]

    # Plot our graph
    ax.clear()  # Must clear so that y max is reset, otherwise, later higher values go up off the plot
    # And because we cleared, we must re-establish these values///
    ax.set_title ("Air Quality PM 2.5 Readings", fontsize=16)
    ax.set_ylabel("EPA Index", fontsize=14)
    ax.grid(True)  # Both grid lines
    ax.margins(x=0)

    if aqi_list[graph_num][1] <= timedelta(minutes=60):
        ax.set_xlabel(f"Previous {int(aqi_list[graph_num][1].total_seconds() / 60)} minutes", fontsize=14)
    elif aqi_list[graph_num][1] <= timedelta(hours=24):
        ax.set_xlabel(f"Previous {int(aqi_list[graph_num][1].total_seconds() / 3600)} hours", fontsize=14)
    elif aqi_list[graph_num][1] <= timedelta(days=365) and graph_year == 365:
        ax.set_xlabel(f"Previous {int(aqi_list[graph_num][1].total_seconds() / 86400)} days", fontsize=14)
    else:
        # We are graphing a full year, Jan - Dec.  Get summary for the year.
        
        query = "SELECT AVG(pm2_5) FROM readings WHERE time BETWEEN ? AND ?"
        cursor.execute(query, (start_date, end_date))
        year_avg = round(cursor.fetchone()[0])

        query = """
        SELECT
            strftime('%Y', time) AS year,
            SUM(CASE WHEN pm2_5 > 150 THEN 1 ELSE 0 END),
            SUM(CASE WHEN pm2_5 > 250 THEN 1 ELSE 0 END)
        FROM readings
        WHERE time BETWEEN ? AND ?
        GROUP BY year;
        """
        cursor.execute(query, (start_date, end_date))
        results = cursor.fetchone()

        # Divisor used below of 1440 = # of minutes in a day.
        days_over_150 = results[1] / 1440
        days_over_250 = results[2] / 1440

        ax.set_xlabel(f"{graph_year}   Average:{year_avg:3.0f},  150+:{days_over_150:5.1f} days,   250+:{days_over_250:5.1f} days", fontsize=14)

    # DB clearnup
    cursor.close()
    conn.close()

    # Even if there is no earlier data to support it, set the width of
    # the graph to the entire date range
    ax.set_xlim(start_date, end_date)
    
    delta = aqi_list[graph_num][1]
    
    if delta <= timedelta(hours=24):
        major_fmt = mdates.DateFormatter('%H:%M')
        if delta <= timedelta(minutes=10):
            major_loc = mdates.MinuteLocator()
        elif delta <= timedelta(minutes=30):
            major_loc = mdates.MinuteLocator(byminute=range(0, 60, 5))
        elif delta <= timedelta(minutes=60):
            major_loc = mdates.MinuteLocator(byminute=range(0, 60, 15))
        elif delta <= timedelta(hours=6):
            major_loc = mdates.HourLocator()
        else:
            major_loc = mdates.HourLocator(byhour=range(0, 24, 3))
        
    elif delta <= timedelta(days=7):
        major_fmt = mdates.DateFormatter('%a')
        major_loc = mdates.DayLocator()
    elif delta <= timedelta(days=30):
        major_fmt = mdates.DateFormatter('%b %d')
        major_loc = mdates.WeekdayLocator(byweekday=mdates.SU)
        minor_loc = mdates.DayLocator()
        ax.xaxis.set_minor_locator(minor_loc)
    else:
        major_fmt = mdates.DateFormatter('%b')
        major_loc = mdates.MonthLocator()

    ax.xaxis.set_major_formatter(major_fmt)
    ax.xaxis.set_major_locator(major_loc)

    series = pd.Series(y)
    y = series.rolling(window=aqi_list[graph_num][2], min_periods=1, center=True).mean()

    ax.plot(x,y)
    
    # get x/y range of plot axes
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    
    # set background colours
    ax.axvspan(xmin, xmax, 0, 50/ymax, facecolor="#D9F8D0")
    ax.axvspan(xmin, xmax, 50/ymax, 100/ymax, facecolor="#FFFFBF")
    ax.axvspan(xmin, xmax, 100/ymax, 150/ymax, facecolor="#FFDEBF")
    ax.axvspan(xmin, xmax, 150/ymax, 200/ymax, facecolor="#FFBFBF")
    ax.axvspan(xmin, xmax, 200/ymax, 300/ymax, facecolor="#D3CDD5")
    ax.axvspan(xmin, xmax, 300/ymax, 1000/ymax, facecolor="#DEBFC7")

    # Show an upper limit of at least 50 and always a low limit of 0.
    ax.set_ylim(top=max(50,ymax))
    ax.set_ylim(bottom=0)

    canvas.draw()


def map_range(value,low_in, high_in, low_out, high_out):
    return int((value-low_in)/(high_in-low_in)*(high_out-low_out)+low_out)
    

def calculate_aqi(pm_sensor_reading):
    # Check sensor reading using EPA breakpoint (Clow-Chigh)
    if 0.0 <= pm_sensor_reading <= 12.0:
        aqi_val = map_range(pm_sensor_reading,0,12,0,50)
    elif 12.0 < pm_sensor_reading <= 35.4:
        aqi_val = map_range(pm_sensor_reading,12,35,51,100)
    elif 35.4 < pm_sensor_reading <= 55.4:
        aqi_val = map_range(pm_sensor_reading,36,55,101,150)
    elif 55.4 < pm_sensor_reading <= 150.4:
        aqi_val = map_range(pm_sensor_reading,56,150,151,200)
    elif 150.4 < pm_sensor_reading <= 250.4:
        aqi_val = map_range(pm_sensor_reading,151,250,201,300)
    elif 250.4 < pm_sensor_reading <= 350.4:
        aqi_val = map_range(pm_sensor_reading,251,350,301,400)
    elif 350.4 < pm_sensor_reading <= 500.4:
        aqi_val = map_range(pm_sensor_reading,351,500,401,500)
    else: 
        aqi_val = pm_sensor_reading
        
    return round(aqi_val)

def get_aqi_color(aqi_index):

    fg = 'black'
    if aqi_index <= 50:
        aqi_color = "#00E400"  # "Good"
    elif aqi_index <= 100:
        aqi_color = "#FFFF00"  # "Moderate" 
    elif aqi_index <= 150:
        aqi_color = "#FF7E00"  # "Unhealthy For Sensitive Groups"
    elif aqi_index <= 200:
        aqi_color = "#FF0000"  # "Unhealthy"
    else:
        fg = 'white'
        if aqi_index <= 300:
            aqi_color = "#99004C"  # "Very Unhealthy"
        else:
            aqi_color = "#7E0023"  # "Hazardous"
        
    return fg, aqi_color

def sample_aq_sensor():
    """
    Samples the PM2.5 sensor over a 2.3 second sample rate
    because sensor outputs data every 1 second but only samples data every 2.3 seconds
    so two quick readings will give same result
    If you imagine the sampling is a full 60 seconds, then this is easier to visulize -
    you are grabbing the average reading for that entire period of time using so many
    readings from the last sample and so many from the current sample
    so in 2.3 seconds, I get readings at 0, 1, 2 seconds (3 readings).  All 3 could have been
    within the same sampling, or maybe only 2 out of 3.  Dividing by 3 will give me that average.
    """

    aq_samples = []
    
    time_start = time.monotonic()
    
    # Sample sensor over 2.3 second sample rate
    while time.monotonic() - time_start <= 2.3:
        try:
            aqdata = pm25.read()
            aq_samples.append(aqdata["pm25 env"])
        except RuntimeError:
            print(("%s  Unable to read from sensor, retrying...") % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            #return -1
            continue
        # Sensor output rate is 1 second
        time.sleep(1)
        
    # average sample reading / # samples
    if len(aq_samples) == 0:
            return -1

    aq_reading = 0

    for sample in range(len(aq_samples)):
        aq_reading += aq_samples[sample]
    aq_reading = aq_reading / len(aq_samples)
    aq_samples.clear()
    return aq_reading

    
def get_aqi():

    # Get raw data from sensor
    raw_pm2_5 = sample_aq_sensor()
    
    if raw_pm2_5 == -1: # reading failed
        MainNum.set("--")
        fg = 'black'
        bg = 'gray'

    else:
        # Convert raw PM2.5 reading to US EPA index value
        aqi_index = calculate_aqi(raw_pm2_5)
        
        now = datetime.now()

        # Connect to SQL DB
        conn = sqlite3.connect("air.db", detect_types=sqlite3.PARSE_DECLTYPES, timeout=30.0)
        
        # Allows readers and a single writer to operate at the same time without blocking each other.
        conn.execute("PRAGMA journal_mode=WAL;")
        
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO readings (time, pm2_5) VALUES (?, ?)",
            (now, aqi_index)
        )
        conn.commit()

        # DB clearnup
        cursor.close()
        conn.close()
        
        # Let's update our IoT feed
        try:
            io_client.send(adafruitIO_feed, aqi_index)
        except Exception as e:
            print(("%s  Adafruit IO failed.\n%s\n") % (now.strftime('%Y-%m-%d %H:%M:%S'),e))

        MainNum.set(aqi_index)
        fg, bg = get_aqi_color(aqi_index)
    
    MainNumStyle.configure('MainNumStyle.TLabel', foreground=fg, background=bg)

    refresh_display(-1) # -1 = user did not click on a button
    # End of get_aqi

def on_closing():
    if askokcancel("Quit Air Quality program?", "Are you sure you want to quit?", icon=WARNING):
        root.quit()

# Main program starts here.

# Create the I2C interface.
i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)

pm25 = PM25_I2C(i2c, None)

# grab Adafruit IoT login information
filename = "config.json"

if os.path.isfile(filename):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            jdata = json.load(file)
    except json.decoder.JSONDecodeError as err:
        print('Invalid config.json file:', err)
        exit(1)
else:
    print('Could not find configuration file:', filename)
    exit(1)

# Using Adafruit IO feed to upload statistics.
adafruitIO_user = jdata["adafruit_IO"]["user"]
adafruitIO_key = jdata["adafruit_IO"]["key"]
adafruitIO_feed = jdata["adafruit_IO"]["feed"]

# Create a REST client instance
io_client = Client(adafruitIO_user,adafruitIO_key)

# Connect to SQL DB
conn = sqlite3.connect("air.db", detect_types=sqlite3.PARSE_DECLTYPES)
cursor = conn.cursor()

# Once in lifetime only - create table
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS readings (
        time TIMESTAMP,
        pm2_5 INTEGER
        )
    """
    )

# DB clearnup
cursor.close()
conn.close()

# Define and initialize arrays
# Button text, graph date range, averaging window
aqi_list = []
aqi_list.append(("10 Min", timedelta(minutes=10),1))
aqi_list.append(("30 Min", timedelta(minutes=30),2))
aqi_list.append(("1 Hour", timedelta(minutes=60),5))
aqi_list.append(("6 Hour", timedelta(hours=6),10))
aqi_list.append(("Day", timedelta(hours=24),20))
aqi_list.append(("Week", timedelta(days=7),30))
aqi_list.append(("Month", timedelta(days=30),45))
aqi_list.append(("Year", timedelta(days=365),60))

# Create the main window
root = Tk()
root.title("Air Quality")

root.rowconfigure(0, weight=1)
root.rowconfigure(1, weight=1)
root.rowconfigure(2, weight=1)

for i in range(len(aqi_list)):
    root.columnconfigure(i, weight=1)

# Set up the fonts we will use
MainNumFont = Font(family = 'Helvetica', size = 30, weight = "bold")
TextFont = Font(family = 'Helvetica', size = 12, weight = "bold")
NumFont = Font(family = 'Helvetica', size = 12, weight = "bold")

# Let's create our own style using any name we want.
MainNumStyle = ttk.Style(root)
MainNumStyle.configure('MainNumStyle.TLabel', font=MainNumFont, anchor='center')
MainNum = IntVar()
# Define the Label that will be used and tell it what style to use
MainNumLabel = ttk.Label(root, textvariable=MainNum, style='MainNumStyle.TLabel')

ButtonStyle = ttk.Style(root)
ButtonStyle.configure('ButtonStyle.TButton', font=TextFont, anchor='center', width=8)

ButtonLabel = []
for i in range(len(aqi_list)):
    ButtonLabel.append(
        ttk.Button(root, text=aqi_list[i][0], command=lambda x=i: refresh_display(x), style='ButtonStyle.TButton'))

AqiStyle = []
for i in range(len(aqi_list)):
    AqiStyle.append(ttk.Style(root))
    
for i in range(len(aqi_list)):
    AqiStyle[i].configure('AqiStyle'+str(i)+'.TLabel', font=NumFont, anchor='center', width = 5)

AqiNum = []
for i in range(len(aqi_list)):
    # This creates a list of IntVar instances.
    # You must use the double brackets.
    AqiNum.append(IntVar())

AqiLabel = []
for i in range(len(aqi_list)):
    AqiLabel.append(ttk.Label(root, textvariable=AqiNum[i], style='AqiStyle'+str(i)+'.TLabel'))

# now, set the window position of each field
MainNumLabel.grid(column=0, row=0, columnspan=len(aqi_list), sticky='EWNS', ipady=5)

for i in range(len(aqi_list)):
    ButtonLabel[i].grid(column=i, row=1, ipady=5, ipadx=5)
    AqiLabel[i].grid(column=i, row=2, ipady=5)

# And for the plot
fig = plt.figure(figsize=(8, 5))

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().grid(row=3, column=0, columnspan=len(aqi_list))

ax = fig.add_subplot(111)

# Set the default graph to Weekly and the year option to normal
i = 0
while (i < len(aqi_list) and aqi_list[i][1] < timedelta(days=7)):
    i += 1
graph_num = i

year_setting = 365 # The year button shows this year.  365 = Current
graph_year = 365 # This is what the graph will be displaying
min_year = -1 # lowest year of data.  After this, go back to current year.

# Call manually to immediately fetch and display first values
get_aqi()

Scheduler = BackgroundScheduler()
Scheduler.start()
Scheduler.add_job(get_aqi,trigger='cron', second=57, id='aqi_job')

root.protocol("WM_DELETE_WINDOW", on_closing)

# Run forever until exit
root.mainloop()

print("Cleaning up and exiting.")

# Stop job upon program exit.  Prevents error after closing.
Scheduler.shutdown()
