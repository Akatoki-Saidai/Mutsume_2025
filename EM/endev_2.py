import json
from logging import getLogger, StreamHandler, Formatter, DEBUG
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import threading
import time

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

logger.info("セットアップを開始します")

if sys.prefix == sys.base_prefix:
    logger.warning("<<警告>>\n仮想環境ではありません")
    time.sleep(3)

logger.info("ライブラリをインポートしています")
from gpiozero import Motor
from picamera2 import Picamera2
import evdev
from evdev import ecodes
import start_gui_2
logger.info("ライブラリのインポート完了")

# =============================
# モーター（ピン配置を前の値に戻した）
# =============================
PIN_R1 = 2
PIN_R2 = 3
PIN_L1 = 17
PIN_L2 = 27

# ★ 前のコードの向きに戻した（右 forward=PIN_R1, 左 forward=PIN_L1）
motor_right = Motor(forward=PIN_R1, backward=PIN_R2)
motor_left  = Motor(forward=PIN_L1, backward=PIN_L2)

throttle = 0.0
steer = 0.0

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def scale_axis_evdev(v: int) -> float:
    center = 127.5
    val = abs(v - center) / center
    if val < 0.15:
        return 0.0
    return clamp(val, 0.0, 1.0)

def update_motors():
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

    logger.debug(f"motors: L={left_power:.2f}, R={right_power:.2f}")

def motor_calib():
    logger.info("モーターキャリブレーション開始")
    motor_left.value = 0
    motor_right.value = 0
    time.sleep(0.3)
    logger.info("キャリブレーション完了")

# =============================
# スピーカー
# =============================
proces_aplay = None

def audio_play(path):
    global proces_aplay
    if proces_aplay is None or proces_aplay.poll() is not None:
        proces_aplay = subprocess.Popen(
            f"aplay --device=hw:1,0 {path}",
            shell=True,
        )
        logger.info("音声再生開始")
    else:
        logger.info("すでに再生中のためスキップ")

# =============================
# コントローラー
# =============================

last_controll_time = time.time()

def start_controller():
    global throttle, steer, last_controll_time

    center = 127.5

    while True:
        device = None
        logger.info("コントローラーを探しています… (PSボタンを押してください)")

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
                    logger.debug("見つかったデバイス: %s",
                        [(d.path, d.name) for d in devices])
            except Exception:
                pass

            if device is None:
                time.sleep(2)

        logger.info(f"接続: {device.path} ({device.name})")

        try:
            device.grab()

            for event in device.read_loop():
                if event.type == ecodes.EV_ABS:
                    # 左スティック Y 軸（前後）
                    if event.code == ecodes.ABS_Y:
                        last_controll_time = time.time()
                        p = scale_axis_evdev(event.value)
                        if p == 0:
                            throttle = 0
                        else:
                            throttle = p if event.value < center else -p
                        logger.debug("ABS_Y raw=%d -> throttle=%.2f", event.value, throttle)
                        update_motors()

                    # 左スティック X 軸（左右）
                    elif event.code == ecodes.ABS_X:
                        last_controll_time = time.time()
                        p = scale_axis_evdev(event.value)
                        if p == 0:
                            steer = 0
                        else:
                            steer = p if event.value > center else -p
                        logger.debug("ABS_X raw=%d -> steer=%.2f", event.value, steer)
                        update_motors()

                elif event.type == ecodes.EV_KEY and event.value == 1:
                    last_controll_time = time.time()

                    if event.code in (ecodes.BTN_SOUTH, 304):
                        logger.info("×ボタン → 非常停止")
                        throttle = steer = 0
                        motor_left.stop()
                        motor_right.stop()
                        audio_play("/home/jaxai/Desktop/GLaDOS_escape_02_entry-00.wav")

                    elif event.code in (ecodes.BTN_WEST, 308):
                        audio_play("/home/jaxai/Desktop/kane_tarinai.wav")

                    elif event.code in (ecodes.BTN_EAST, 305):
                        audio_play("/home/jaxai/Desktop/hatodokei.wav")

                    elif event.code in (ecodes.BTN_NORTH, 307):
                        audio_play("/home/jaxai/Desktop/otoko_ou!.wav")

        except Exception as e:
            logger.error(f"Controller error: {e}")
            time.sleep(1)
        finally:
            try:
                device.ungrab()
            except Exception:
                pass

# =============================
# GUI 読み書き
# =============================

def read_from_gui():
    global last_controll_time
    if time.time() - last_controll_time < 1:
        return
    try:
        with open("data_from_browser.json") as f:
            d = json.load(f)
        motor_left.value = float(d["motor_l"])
        motor_right.value = float(d["motor_r"])
    except:
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
    except:
        pass

def update_gui():
    while True:
        try:
            read_from_gui()
            write_to_gui()
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"GUI error: {e}")

# =============================
# カメラ
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
            logger.error(f"Camera error: {e}")

# =============================
# 起動処理
# =============================

logger.info("モーターキャリブレーション開始")
motor_calib()

threading.Thread(target=start_controller, daemon=True).start()
threading.Thread(target=start_gui_2.start_server, kwargs={"logger": logger}, daemon=True).start()
threading.Thread(target=update_gui, daemon=True).start()
threading.Thread(target=start_camera, daemon=True).start()

logger.info("すべてのセットアップ完了")

while True:
    time.sleep(10)
