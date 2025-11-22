import json
from logging import getLogger, StreamHandler, Formatter, DEBUG
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import threading
import time

# --------------------------------------------------------------------
# basic setup
# --------------------------------------------------------------------
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
    logger.warning("<<警告>> virtualenv ではありません")
    time.sleep(1)

logger.info("importing libraries")
from gpiozero import Motor
from picamera2 import Picamera2
import evdev
from evdev import ecodes
import start_gui_2
logger.info("libraries imported")

# --------------------------------------------------------------------
# motors (same mapping as MyController)
# --------------------------------------------------------------------
PIN_AIN1 = 2
PIN_AIN2 = 3
PIN_BIN1 = 17
PIN_BIN2 = 27

# same as:
#   self.motor_left  = Motor(forward=PIN_AIN2, backward=PIN_AIN1)
#   self.motor_right = Motor(forward=PIN_BIN2, backward=PIN_BIN1)
motor_left  = Motor(forward=PIN_AIN2, backward=PIN_AIN1)
motor_right = Motor(forward=PIN_BIN2, backward=PIN_BIN1)

throttle = 0.0  # forward/back (-1.0 .. +1.0)
steer = 0.0     # left/right   (-1.0 .. +1.0)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def scale_axis_evdev(v: int) -> float:
    """
    Convert evdev ABS_* (0..255, center~127.5) to |value| 0.0..1.0.
    Same concept as MyController.scale_axis().
    """
    center = 127.5
    mag = abs(v - center) / center  # 0.0 .. 1.0

    # dead zone
    if mag < 0.15:
        return 0.0

    return clamp(mag, 0.0, 1.0)


def update_motors():
    """
    Same logic as MyController.update_motors():

        left_power  = throttle + steer
        right_power = throttle - steer
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
        "motors: L=%.2f R=%.2f (throttle=%.2f, steer=%.2f)",
        left_power, right_power, throttle, steer
    )


def motor_init():
    logger.info("motor init: stop both")
    motor_left.stop()
    motor_right.stop()
    time.sleep(0.3)
    logger.info("motor init done")


# --------------------------------------------------------------------
# speaker
# --------------------------------------------------------------------
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


# --------------------------------------------------------------------
# controller (evdev version of MyController)
# --------------------------------------------------------------------
last_controll_time = time.time()


def start_controller():
    """
    Reproduce MyController behavior with evdev.

    - ABS_Y: up   -> throttle = +p
             down -> throttle = -p
    - ABS_X: right -> steer = +p
             left  -> steer = -p
    - BTN_SOUTH (×): emergency stop
    """
    global throttle, steer, last_controll_time

    center = 127.5

    while True:
        device = None
        logger.info("searching PS4 controller... (press PS button)")

        # find correct input device (exclude Touchpad-only)
        while device is None:
            try:
                devices = [evdev.InputDevice(p) for p in evdev.list_devices()]
                candidates = [
                    d for d in devices
                    if "Wireless Controller" in d.name and "Touchpad" not in d.name
                ]
                if candidates:
                    device = candidates[0]
                else:
                    logger.debug(
                        "available devices: %s",
                        [(d.path, d.name) for d in devices]
                    )
            except Exception as e:
                logger.error("device listing error: %s", e)

            if device is None:
                time.sleep(2)

        logger.info("controller connected: %s (%s)", device.path, device.name)

        try:
            device.grab()

            for event in device.read_loop():
                # debug all events (first stage)
                logger.debug("event: type=%d code=%d value=%d",
                             event.type, event.code, event.value)

                # analog sticks
                if event.type == ecodes.EV_ABS:

                    # left stick Y (forward/back)
                    if event.code == ecodes.ABS_Y:
                        last_controll_time = time.time()
                        p = scale_axis_evdev(event.value)

                        if p == 0.0:
                            throttle = 0.0
                        else:
                            if event.value < center:
                                # up -> forward
                                throttle = p
                            else:
                                # down -> backward
                                throttle = -p

                        logger.info("ABS_Y: raw=%d -> throttle=%.2f",
                                    event.value, throttle)
                        update_motors()

                    # left stick X (left/right)
                    elif event.code == ecodes.ABS_X:
                        last_controll_time = time.time()
                        p = scale_axis_evdev(event.value)

                        if p == 0.0:
                            steer = 0.0
                        else:
                            if event.value > center:
                                # right
                                steer = p
                            else:
                                # left
                                steer = -p

                        logger.info("ABS_X: raw=%d -> steer=%.2f",
                                    event.value, steer)
                        update_motors()

                # buttons
                elif event.type == ecodes.EV_KEY and event.value == 1:
                    last_controll_time = time.time()
                    logger.info("button pressed: code=%d", event.code)

                    # × button -> emergency stop
                    if event.code in (ecodes.BTN_SOUTH, 304):
                        logger.info("X pressed: EMERGENCY STOP")
                        throttle = 0.0
                        steer = 0.0
                        motor_left.stop()
                        motor_right.stop()
                        audio_play(
                            "/home/jaxai/Desktop/GLaDOS_escape_02_entry-00.wav"
                        )

                    elif event.code in (ecodes.BTN_WEST, 308):
                        audio_play("/home/jaxai/Desktop/kane_tarinai.wav")

                    elif event.code in (ecodes.BTN_EAST, 305):
                        audio_play("/home/jaxai/Desktop/hatodokei.wav")

                    elif event.code in (ecodes.BTN_NORTH, 307):
                        audio_play("/home/jaxai/Desktop/otoko_ou!.wav")

        except Exception as e:
            logger.error("controller error: %s", e)
            time.sleep(1)
        finally:
            try:
                device.ungrab()
            except Exception:
                pass


# --------------------------------------------------------------------
# GUI (motors are NOT overridden by GUI for now)
# --------------------------------------------------------------------
def read_from_gui():
    # do not overwrite motors from GUI while debugging controller
    try:
        with open("data_from_browser.json") as f:
            _ = json.load(f)
    except Exception:
        pass


def write_to_gui():
    try:
        with open("data_to_browser.json") as f:
            d = json.load(f)
        # expose current motor values to browser
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


# --------------------------------------------------------------------
# camera
# --------------------------------------------------------------------
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


# --------------------------------------------------------------------
# startup
# --------------------------------------------------------------------
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
