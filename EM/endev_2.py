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

# your original mapping:
# self.motor_left  = Motor(forward=PIN_AIN2, backward=PIN_AIN1)
# self.motor_right = Motor(forward=PIN_BIN2, backward=PIN_BIN1)
motor_left = Motor(forward=PIN_AIN2, backward=PIN_AIN1)
motor_right = Motor(forward=PIN_BIN2, backward=PIN_BIN1)

# left stick state
throttle = 0.0  # forward/back (-1..+1)
steer = 0.0     # left/right  (-1..+1)

# controller vs GUI 優先度用
last_controll_time = time.time()


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


def update_motors_from_state():
    """
    Same motor mixing as your MyController.update_motors():
        left  = throttle + steer
        right = throttle - steer
    """
    global throttle, steer

    left_power = throttle + steer
    right_power = throttle - steer

    left_power = clamp(left_power, -1.0, 1.0)
    right_power = clamp(right_power, -1.0, 1.0)

    if abs(left_power) < 0.01 and abs(right_power) < 0.01:
        motor_left.stop()
        motor_right.stop()
    else:
        motor_left.value = left_power
        motor_right.value = right_power

    logger.debug(
        "motors: L=%.2f R=%.2f (throttle=%.2f steer=%.2f)",
        left_power, right_power, throttle, steer
    )


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
# PS4 controller (your MyController, integrated)
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
        global throttle, last_controll_time
        p = scale_axis(value)
        self.throttle = p
        throttle = self.throttle
        last_controll_time = time.time()
        self.update_motors()

    def on_L3_down(self, value):
        global throttle, last_controll_time
        p = scale_axis(value)
        self.throttle = -p
        throttle = self.throttle
        last_controll_time = time.time()
        self.update_motors()

    def on_L3_y_at_rest(self):
        global throttle, last_controll_time
        self.throttle = 0.0
        throttle = 0.0
        last_controll_time = time.time()
        self.update_motors()

    # ----- left stick X -----
    def on_L3_right(self, value):
        global steer, last_controll_time
        p = scale_axis(value)
        self.steer = p
        steer = self.steer
        last_controll_time = time.time()
        self.update_motors()

    def on_L3_left(self, value):
        global steer, last_controll_time
        p = scale_axis(value)
        self.steer = -p
        steer = self.steer
        last_controll_time = time.time()
        self.update_motors()

    def on_L3_x_at_rest(self):
        global steer, last_controll_time
        self.steer = 0.0
        steer = 0.0
        last_controll_time = time.time()
        self.update_motors()

    # ----- X button (emergency stop) -----
    def on_x_press(self):
        global throttle, steer, last_controll_time
        self.throttle = 0.0
        self.steer = 0.0
        throttle = 0.0
        steer = 0.0
        self.motor_left.stop()
        self.motor_right.stop()
        last_controll_time = time.time()
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
        # 同期のため global にも反映
        global throttle, steer
        throttle = self.throttle
        steer = self.steer


def start_controller():
    controller = MyController(
        interface="/dev/input/js0",
        connecting_using_ds4drv=False,
    )
    logger.info("Listening PS4 controller (left stick)...")
    controller.listen()


# =============================
# GUI (controller優先でモーターは書き換え)
# =============================

def read_from_gui():
    global throttle, steer, last_controll_time

    # controller入力から 1 秒以内は GUI からの上書きを無視
    if time.time() - last_controll_time < 1.0:
        return

    try:
        with open("data_from_browser.json") as f:
            d = json.load(f)
        # GUI からは direct に motor value を指定（-1..+1）
        motor_left.value = float(d["motor_l"])
        motor_right.value = float(d["motor_r"])
        # global 状態も合わせておく
        # ここは簡単に「平均」としておく（厳密でなくてOK）
        throttle = (motor_left.value + motor_right.value) / 2.0
        steer = (motor_left.value - motor_right.value) / 2.0
    except Exception:
        pass


def write_to_gui():
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
            read_from_gui()
            write_to_gui()
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
