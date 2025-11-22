import json
from logging import getLogger, StreamHandler, Formatter, DEBUG
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import threading
import time

# =============================
# basic setup
# =============================
os.chdir(os.path.dirname(__file__))

try:
    os.remove("print.txt")
    os.remove("fm.log")
except Exception:
    pass

sys.stdout = open("print.txt", "w")

logger = getLogger(__name__)
logger.setLevel(DEBUG)
logger.propagate = False

s_handler = StreamHandler()
s_handler.setLevel(DEBUG)
logger.addHandler(s_handler)

tsv_format = Formatter(
    "%(asctime)s.%(msecs)d+09:00\t%(name)s\t%(filename)s\t%(lineno)d\t%(funcName)s\t%(levelname)s\t%(message)s",
    "%Y-%m-%dT%H:%M:%S",
)
f_handler = RotatingFileHandler("fm.log", maxBytes=100 * 1000)
f_handler.setLevel(DEBUG)
f_handler.setFormatter(tsv_format)
logger.addHandler(f_handler)

logger.info("setup start")

if sys.prefix == sys.base_prefix:
    logger.warning("WARNING: not running in virtualenv")
    time.sleep(1)

logger.info("importing libraries")
from gpiozero import Motor
from picamera2 import Picamera2
from pyPS4Controller.controller import Controller
import start_gui_2
logger.info("libraries imported")

# =============================
# motors (same as your MyController)
# =============================

PIN_AIN1 = 2
PIN_AIN2 = 3
PIN_BIN1 = 17
PIN_BIN2 = 27

motor_left = Motor(forward=PIN_AIN2, backward=PIN_AIN1)
motor_right = Motor(forward=PIN_BIN2, backward=PIN_BIN1)

# left stick state
throttle = 0.0  # forward/back (-1..+1)
steer = 0.0     # left/right  (-1..+1)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def scale_axis(v: int) -> float:
    """
    Same idea as your scale_axis:
    PS4 axis value (-32768 .. 32767) -> |value| 0.0 .. 1.0 (with deadzone)
    """
    v = abs(v)
    val = v / 32767.0
    if val < 0.15:
        return 0.0
    return clamp(val, 0.0, 1.0)


def motor_init():
    logger.info("motor init: stop both")
    motor_left.stop()
    motor_right.stop()
    time.sleep(0.3)
    logger.info("motor init done")


# =============================
# speaker (optional)
# =============================

proces_aplay = None


def audio_play(path: str):
    global proces_aplay
    if proces_aplay is None or proces_aplay.poll() is not None:
        proces_aplay = subprocess.Popen(
            f"aplay --device=hw:1,0 {path}",
            shell=True,
        )
        logger.info("audio play: %s", path)
    else:
        logger.info("audio already playing, skip")


# =============================
# PS4 controller (your MyController)
# =============================

class MyController(Controller):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # use global motors
        self.motor_left = motor_left
        self.motor_right = motor_right

        self.throttle = 0.0  # forward/back
        self.steer = 0.0     # left/right

        print("Motors initialized, waiting for controller...")

    # ----- left stick Y -----
    def on_L3_up(self, value):
        p = scale_axis(value)
        self.throttle = p
        self.update_motors()

    def on_L3_down(self, value):
        p = scale_axis(value)
        self.throttle = -p
        self.update_motors()

    def on_L3_y_at_rest(self):
        self.throttle = 0.0
        self.update_motors()

    # ----- left stick X -----
    def on_L3_right(self, value):
        p = scale_axis(value)
        self.steer = p
        self.update_motors()

    def on_L3_left(self, value):
        p = scale_axis(value)
        self.steer = -p
        self.update_motors()

    def on_L3_x_at_rest(self):
        self.steer = 0.0
        self.update_motors()

    # ----- X button (emergency stop) -----
    def on_x_press(self):
        self.throttle = 0.0
        self.steer = 0.0
        self.motor_left.stop()
        self.motor_right.stop()
        print("X pressed: EMERGENCY STOP")
        # audio_play("/home/jaxai/Desktop/GLaDOS_escape_02_entry-00.wav")

    def update_motors(self):
        """
        exactly your update_motors()
        """
        left_power = self.throttle + self.steer
        right_power = self.throttle - self.steer

        left_power = clamp(left_power, -1.0, 1.0)
        right_power = clamp(right_power, -1.0, 1.0)

        if abs(left_power) < 0.01 and abs(right_power) < 0.01:
            self.motor_left.stop()
            self.motor_right.stop()
        else:
            self.motor_left.value = left_power
            self.motor_right.value = right_power

        logger.debug(
            "motors(MyController): L=%.2f R=%.2f (thr=%.2f steer=%.2f)",
            left_power, right_power, self.throttle, self.steer
        )


def start_controller():
    controller = MyController(
        interface="/dev/input/js0",
        connecting_using_ds4drv=False,
    )
    logger.info("Listening PS4 controller (left stick)...")
    controller.listen()


# =============================
# GUI (no control over motors, only status output)
# =============================

def read_from_gui():
    # ignore any commands from browser (no motor control via GUI)
    try:
        with open("data_from_browser.json") as f:
            _ = json.load(f)
    except Exception:
        pass


def write_to_gui():
    # only expose current motor values to browser
    try:
        with open("data_to_browser.json") as f:
            d = json.load(f)
        d["motor_l"] = motor_left.value
        d["motor_r"] = motor_right.value
        d["light"] = False
        d["buzzer"] = False
        with open("data_to_browser.json", "w") as f:
            f.write(json.dumps(d))
    except Exception:
        pass


def update_gui():
    while True:
        try:
            read_from_gui()   # just to keep file fresh / avoid errors
            write_to_gui()    # send current motor state to browser
            time.sleep(0.5)
        except Exception as e:
            logger.error("GUI error: %s", e)


# =============================
# camera
# =============================

picam2 = Picamera2()
cfg = picam2.create_preview_configuration()
picam2.configure(cfg)
picam2.start()


def start_camera():
    while True:
        try:
            picam2.capture_file("camera_temp.jpg")
            os.replace("camera_temp.jpg", "camera.jpg")
            time.sleep(0.1)
        except Exception as e:
            logger.error("Camera error: %s", e)


# =============================
# startup
# =============================

logger.info("motor init")
motor_init()

threading.Thread(target=start_controller, daemon=True).start()
threading.Thread(
    target=start_gui_2.start_server,
    kwargs={"logger": logger},
    daemon=True,
).start()
threading.Thread(target=update_gui, daemon=True).start()
threading.Thread(target=start_camera, daemon=True).start()

logger.info("all systems started")

while True:
    time.sleep(10)
