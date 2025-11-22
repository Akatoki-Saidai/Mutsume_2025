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

logger.info("セットアップ開始")

if sys.prefix == sys.base_prefix:
    logger.warning("<<警告>> 仮想環境で実行されていません")
    time.sleep(2)

logger.info("ライブラリ読み込み中")
from gpiozero import Motor
from picamera2 import Picamera2
import evdev
from evdev import ecodes
import start_gui_2
logger.info("ライブラリ読み込み完了")

# =============================
# モーター（あなたのピン配置のまま）
# =============================
PIN_R1 = 2
PIN_R2 = 3
PIN_L1 = 17
PIN_L2 = 27

motor_right = Motor(forward=PIN_R1, backward=PIN_R2)
motor_left  = Motor(forward=PIN_L1, backward=PIN_L2)

# スティック状態
throttle = 0.0
steer = 0.0

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def scale_axis_evdev(v: int):
    center = 127.5
    val = (v - center) / center  # -1.0〜1.0
    if abs(val) < 0.1:
        return 0.0
    return clamp(val, -1.0, 1.0)

# =============================
# ★ RCカー自然動作 update_motors ★
# =============================
def update_motors():
    global throttle, steer

    # 前後のみ
    if abs(steer) < 0.05:
        motor_left.value = throttle
        motor_right.value = throttle
        logger.debug(f"直進/後退: L={motor_left.value:.2f} R={motor_right.value:.2f}")
        return

    # 左右のみ
    if abs(throttle) < 0.05:
        # 右旋回 → 右停止＋左前進
        if steer > 0:
            motor_left.value = steer
            motor_right.value = 0
        else:
            motor_left.value = 0
            motor_right.value = -steer
        logger.debug(f"旋回: L={motor_left.value:.2f} R={motor_right.value:.2f}")
        return

    # 同時操作 → カーブ
    if steer > 0:
        motor_left.value = throttle
        motor_right.value = throttle * (1 - steer)
    else:
        motor_left.value = throttle * (1 + steer)
        motor_right.value = throttle

    logger.debug(f"カーブ: L={motor_left.value:.2f} R={motor_right.value:.2f}")

# =============================
# スピーカー
# =============================
proces_aplay = None
def audio_play(path):
    global proces_aplay
    if proces_aplay is None or proces_aplay.poll() is not None:
        proces_aplay = subprocess.Popen(
            f"aplay --device=hw:1,0 {path}",
            shell=True)
        logger.info("音声再生")
    else:
        logger.info("すでに再生中")

# =============================
# コントローラ
# =============================
last_controll_time = time.time()

def start_controller():
    global throttle, steer, last_controll_time

    while True:
        device = None
        logger.info("コントローラー検索中… PSボタンを押してください")

        while device is None:
            try:
                devices = [evdev.InputDevice(p) for p in evdev.list_devices()]
                candidates = [d for d in devices
                              if "Wireless Controller" in d.name
                              and "Touchpad" not in d.name]
                if candidates:
                    device = candidates[0]
            except:
                pass
            if device is None:
                time.sleep(2)

        logger.info(f"接続: {device.path} ({device.name})")

        try:
            device.grab()
            for event in device.read_loop():

                # アナログスティック
                if event.type == ecodes.EV_ABS:
                    # 前後：ABS_Y（上が前）
                    if event.code == ecodes.ABS_Y:
                        last_controll_time = time.time()
                        throttle = -scale_axis_evdev(event.value)  # 上が前なので反転
                        update_motors()

                    # 左右：ABS_X
                    elif event.code == ecodes.ABS_X:
                        last_controll_time = time.time()
                        steer = scale_axis_evdev(event.value)
                        update_motors()

                # ボタン
                elif event.type == ecodes.EV_KEY and event.value == 1:
                    last_controll_time = time.time()

                    # ×ボタン → 停止
                    if event.code in (ecodes.BTN_SOUTH, 304):
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
            logger.error(f"controller error: {e}")
            time.sleep(1)
        finally:
            try:
                device.ungrab()
            except:
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
        read_from_gui()
        write_to_gui()
        time.sleep(0.5)

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
            logger.error(f"camera error: {e}")

# =============================
# 起動処理
# =============================
logger.info("モーター初期化")
motor_left.value = 0
motor_right.value = 0
time.sleep(0.3)

threading.Thread(target=start_controller, daemon=True).start()
threading.Thread(target=start_gui_2.start_server, kwargs={"logger": logger}, daemon=True).start()
threading.Thread(target=update_gui, daemon=True).start()
threading.Thread(target=start_camera, daemon=True).start()

logger.info("全システム起動完了")

while True:
    time.sleep(10)
