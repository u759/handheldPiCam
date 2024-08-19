from PyQt5 import QtCore
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)
from PyQt5.QtGui import QFont
from picamera2 import Picamera2
from picamera2.previews.qt import QGlPicamera2
from libcamera import controls
import threading
import sys
import os
import uuid
import pygame
from pygame.locals import *
import RPi.GPIO as GPIO
import numpy as np
from PIL import Image
import glob

current_image_index = 0
image_files = []

def image_list():
    global current_image_index
    global image_files
    usb_image_directory = '/media/raspberrypi/USB'
    image_files = sorted(glob.glob(os.path.join(usb_image_directory, '*.jpg')), key=os.path.getctime)
    current_image_index = len(image_files) - 1

def post_callback(request):
    metadata = request.get_metadata()
    exposure_time = metadata.get('ExposureTime', 'N/A')
    analogue_gain = metadata.get('AnalogueGain', 'N/A')
    speed_label.setText(f"Shutter Speed: {displaySpeed(exposure_time)}")
    iso_label.setText(f"Gain: {round(analogue_gain)}")

    global current_iso, current_speed, awb
    current_iso = analogue_gain
    current_speed = exposure_time

def auto_exposure_mode():
    picam2.set_controls({"AeEnable": True})
    picam2.set_controls({"AwbEnable": True})
    picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})

def displaySpeed(speed):
    if speed * pow(10, -6) < 1:
        return "1/" + str(round(1/(speed * pow(10, -6))))
    return str(round(speed * pow(10, -6)))

def capture_done(job):
    picam2.wait(job)
    capture_button.setEnabled(True)
    GPIO.add_event_detect(GPIO_CAPTURE_PIN, GPIO.FALLING, callback=on_button_clicked, bouncetime=300)  # Re-enable GPIO event detection

def on_button_clicked(channel):
    pygame.display.quit()
    pygame.quit()
    global unique_filename
    if os.path.exists("/media/raspberrypi/USB"):
        capture_button.setEnabled(False)
        GPIO.remove_event_detect(GPIO_CAPTURE_PIN)  # Disable GPIO event detection
        image_array = picam2.switch_mode_and_capture_array(full_res_config)
        unique_filename = f"/media/raspberrypi/USB/{uuid.uuid4()}.jpg"
        save_image(image_array, unique_filename)
        capture_button.setEnabled(True)
        GPIO.add_event_detect(GPIO_CAPTURE_PIN, GPIO.FALLING, callback=on_button_clicked, bouncetime=300)  # Re-enable GPIO event detection

def save_image(image_array, filename):
    image = Image.fromarray(image_array)
    image.save(filename)

def on_playback_clicked():
    GPIO.remove_event_detect(GPIO_CAPTURE_PIN)
    GPIO.remove_event_detect(GPIO_FOCUS_PIN)
    if os.path.exists("/media/raspberrypi/USB"):
        def playback_task():
            global image, unique_filename, current_image_index, image_files
            image_list()
            pygame.init()
            pygame.font.init()  # Initialize the font module
            font = pygame.font.SysFont('Arial', 24)  # Create a font object
            window_size = (590, 440)
            scrn = pygame.display.set_mode(window_size)
            pygame.display.set_caption('Playback')

            def display_image(image_path):
                imp = pygame.image.load(image_path)
                imp = pygame.transform.scale(imp, window_size)
                scrn.blit(imp, (0, 0))
                text_surface = font.render(f'{current_image_index + 1}/{len(image_files)}', True, (255, 255, 255), (0, 0, 0))
                scrn.blit(text_surface, (10, 10))  # Position the text at (10, 10)
                pygame.display.flip()

            display_image(image_files[current_image_index])

            status = True
            while (status):
            # iterate over the list of Event objects
            # that was returned by pygame.event.get() method.
                for i in pygame.event.get():
            
                    # if event object type is QUIT
                    # then quitting the pygame
                    # and program both.
                    if i.type == pygame.QUIT:
                        status = False
                    if i.type == pygame.MOUSEBUTTONDOWN:
                        status = False

                if GPIO.input(GPIO_FOCUS_PIN) == GPIO.LOW and os.path.exists("/media/raspberrypi/USB"):  # Focus button pressed
                    current_image_index = (current_image_index - 1) % len(image_files)
                    unique_filename = image_files[current_image_index]
                    display_image(unique_filename)
                    while GPIO.input(GPIO_FOCUS_PIN) == GPIO.LOW:
                        pass  # Wait for button release

                if GPIO.input(GPIO_CAPTURE_PIN) == GPIO.LOW and os.path.exists("/media/raspberrypi/USB"):  # Capture button pressed
                    current_image_index = (current_image_index + 1) % len(image_files)
                    unique_filename = image_files[current_image_index]
                    display_image(unique_filename)
                    while GPIO.input(GPIO_CAPTURE_PIN) == GPIO.LOW:
                        pass  # Wait for button release

                if os.path.exists("/media/raspberrypi/USB") == False:
                    status = False
 
            # deactivates the pygame library
            pygame.display.quit()
            pygame.quit()
            GPIO.add_event_detect(GPIO_CAPTURE_PIN, GPIO.FALLING, callback=on_button_clicked, bouncetime=300)
            GPIO.add_event_detect(GPIO_FOCUS_PIN, GPIO.FALLING, callback=autofocus, bouncetime=300)
        threading.Thread(target=playback_task).start()

def autofocus(channel):
    pygame.display.quit()
    pygame.quit()
    def autofocus_task():
        capture_button.setEnabled(False)  # Disable the capture button
        picam2.set_controls({"AfMode": controls.AfModeEnum.Auto})
        job = picam2.autofocus_cycle(wait=False)
        success = picam2.wait(job)
        capture_button.setEnabled(True)  # Re-enable the capture button

    threading.Thread(target=autofocus_task).start()

def increase_iso():
    global current_iso
    current_iso = min(current_iso + 1, 8)  # Assuming max ISO value is 8
    picam2.set_controls({'AnalogueGain': current_iso})

def decrease_iso():
    global current_iso
    current_iso = max(current_iso - 1, 1)  # Assuming min ISO value is 1
    picam2.set_controls({'AnalogueGain': current_iso})

def increase_speed():
    global current_speed
    current_speed = min(current_speed * 2, 100000)
    picam2.set_controls({'ExposureTime': round(current_speed)})

def decrease_speed():
    global current_speed
    current_speed = max(current_speed / 2, 2/3*1000)
    picam2.set_controls({'ExposureTime': round(current_speed)})

# GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO_CAPTURE_PIN = 21  # Use the GPIO pin number you want to use
GPIO_FOCUS_PIN = 16
GPIO.setup(GPIO_CAPTURE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_FOCUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

app = QApplication(sys.argv)

current_iso = 0
current_speed = 0
unique_filename = ""
picam2 = Picamera2()

picam2.set_controls({"AnalogueGain": current_iso})
picam2.set_controls({"NoiseReductionMode": controls.draft.NoiseReductionModeEnum.HighQuality})
picam2.set_controls({"Sharpness": 8.0})
picam2.post_callback = post_callback

# Set preview configuration with adjusted aspect ratio
preview_config = picam2.create_preview_configuration(main={"size": (640, 480)}, raw={"size": picam2.sensor_resolution})  # 4:3 aspect ratio
picam2.configure(preview_config)

# Set capture configuration for full resolution (16MP)
full_res_config = picam2.create_still_configuration(main={"size": picam2.sensor_resolution}, buffer_count=1)

# Create the preview widget
qpicamera2 = QGlPicamera2(picam2, width=640, height=480, keep_ar=True)

# Layout for the controls
controls_layout = QVBoxLayout()

# Example buttons for camera control
AF_button = QPushButton("Focus")
capture_button = QPushButton("Capture")
playback_button = QPushButton("Playback")

# Exposure mode toggle button
exposure_toggle_button = QPushButton("Auto")

# Shutter speed adjustment buttons
speed_label = QLabel()
speed_increase_button = QPushButton("+")
speed_decrease_button = QPushButton("-")

# ISO adjustment buttons
iso_label = QLabel()
iso_increase_button = QPushButton("+")
iso_decrease_button = QPushButton("-")

# Create a horizontal layout for the speed adjustment buttons
speed_buttons_layout = QHBoxLayout()
speed_buttons_layout.addWidget(speed_increase_button)
speed_buttons_layout.addWidget(speed_decrease_button)

# Create a horizontal layout for the ISO adjustment buttons
iso_buttons_layout = QHBoxLayout()
iso_buttons_layout.addWidget(iso_increase_button)
iso_buttons_layout.addWidget(iso_decrease_button)

#Create a horizontal layout for the capture/playback button
capture_playback_layout = QHBoxLayout()
capture_playback_layout.addWidget(capture_button)
capture_playback_layout.addWidget(playback_button)

# Adding buttons to the layout
controls_layout.addWidget(exposure_toggle_button)
controls_layout.addWidget(speed_label)
controls_layout.addLayout(speed_buttons_layout)
controls_layout.addWidget(iso_label)
controls_layout.addLayout(iso_buttons_layout)
controls_layout.addWidget(AF_button)
controls_layout.addLayout(capture_playback_layout)

# Set a fixed height for the buttons
button_height = 50  # Adjust the height as needed

exposure_toggle_button.setFixedHeight(button_height)
speed_increase_button.setFixedHeight(button_height)
speed_decrease_button.setFixedHeight(button_height)
iso_increase_button.setFixedHeight(button_height)
iso_decrease_button.setFixedHeight(button_height)
AF_button.setFixedHeight(button_height)
capture_button.setFixedHeight(button_height + 20)
playback_button.setFixedHeight(button_height + 20)

# Connect button to the function
capture_button.clicked.connect(on_button_clicked)
playback_button.clicked.connect(on_playback_clicked)
AF_button.clicked.connect(autofocus)
exposure_toggle_button.clicked.connect(auto_exposure_mode)

# Connect ISO adjustment buttons to their functions
iso_increase_button.clicked.connect(increase_iso)
iso_decrease_button.clicked.connect(decrease_iso)

# Connect speed adjustment buttons to their functions
speed_increase_button.clicked.connect(increase_speed)
speed_decrease_button.clicked.connect(decrease_speed)

# Set font size
font = QFont()
font.setPointSize(12)  # Adjust the font size as needed

fontButton = QFont()
fontButton.setPointSize(20)  # Adjust the font size as needed


# Apply font to widgets
AF_button.setFont(font)
capture_button.setFont(font)
playback_button.setFont(font)
exposure_toggle_button.setFont(font)
speed_label.setFont(font)
speed_increase_button.setFont(fontButton)
speed_decrease_button.setFont(fontButton)
iso_label.setFont(font)
iso_increase_button.setFont(fontButton)
iso_decrease_button.setFont(fontButton)

# Add event detection for the GPIO pin
GPIO.add_event_detect(GPIO_CAPTURE_PIN, GPIO.FALLING, callback=on_button_clicked, bouncetime=300)
GPIO.add_event_detect(GPIO_FOCUS_PIN, GPIO.FALLING, callback=autofocus, bouncetime=300)

# Create the label for metadata display
label = QLabel()
label.setFixedWidth(120)
label.setAlignment(QtCore.Qt.AlignTop)

# Add the label to the controls layout
controls_layout.addWidget(label)

# Main layout
main_layout = QHBoxLayout()
main_layout.addWidget(qpicamera2, 90)
main_layout.addLayout(controls_layout, 10)

# Set the central widget
central_widget = QWidget()
central_widget.setLayout(main_layout)

# Create the main window
window = QWidget()
window.setWindowTitle("Qt Picamera2 App")
window.setLayout(main_layout)

# Start the camera
picam2.start()

#Custom settings
picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
picam2.options["quality"] = 95

# Show the window in fullscreen mode
window.showFullScreen()

sys.exit(app.exec_())
