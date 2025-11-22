import json
from logging import getLogger, StreamHandler, Formatter, DEBUG
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import threading
import time

# このスクリプトの場所をカレントディレクトリに
os.chdir(os.path.dirname(__file__))

# ログファイル初期化
try:
    os.remove("print.txt")
    os.remove("fm.log")
except Exception:
    pass

# 標準出力をファイルに逃がす
sys.stdout = open("print.txt", "w")

# ロガー設定
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

# 仮想環境チェック
if sys.prefix == sys.base_prefix:
    logger.warning("<<警告>>\n仮想環境ではありません")
    time.sleep(5)

# ==== ライブラリ ====
logger.info("ライブラリをインポートしています")
from gpiozero import Motor
from picamera2 import Picamera2
import evdev
from evdev import ecodes
import start_gui_2
logger.info("ライブラリのインポート完了")

# =============================
# モーター
# =============================

PIN_R1 = 2
PIN_R2 = 3
PIN_L1 = 17
PIN_L2 = 27

# pigpio 不使用版（デフォルトバックエンド）
motor_right = Motor(forward=PIN_R1, backward=PIN_R2)
motor_left = Motor(forward=PIN_L1, backward=PIN_L2)

# 左スティック状態
throttle = 0.0  # 前後（上＋、下−）
steer = 0.0     # 左右（右＋、左−）


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def scale_axis_evdev(v: int) -> float:
    """
    evdev の ABS_*（0〜255, center ≒127.5）を 0.0〜1.0 に正規化。
    絶対値だけを返す（向きは呼び出し側で決める）。
    """
    center = 127.5
    val = abs(v - center) / center
    if val < 0.15:
        return 0.0
    return clamp(val, 0.0, 1.0)


def update_motors():
    """
    throttle（前後）と steer（左右）から左右の出力を決める差動制御。
    pyPS4Controller 版と同じロジック。
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

    logger.debug(f"L={left_power:.2f} R={right_power:.2f}")


def motor_calib():
    """
    今は簡易版：全部停止だけ（必要なら前後テストをここに追加）
    """
    logger.info("モーターキャリブレーション開始")
    motor_left.value = 0
    motor_right.value = 0
    time.sleep(0.5)
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

        # デバイス探索
        while device is None:
            try:
                for dev in [evdev.InputDevice(p) for p in evdev.list_devices()]:
                    if "Wireless Controller" in dev.name:
                        device = dev
                        break
            except Exception:
                pass

            if device is None:
                time.sleep(2)

        logger.info(f"接続: {device.path} ({device.name})")
        try:
            device.grab()

            for event in device.read_loop():
                # アナログスティック
                if event.type == ecodes.EV_ABS:
                    # 左スティック Y（前後）
                    if event.code == ecodes.ABS_Y:
                        last_controll_time = time.time()
                        p = scale_axis_evdev(event.value)
                        if p == 0.0:
                            throttle = 0.0
                        else:
                            if event.value < center:
                                throttle = p      # 上 = 前進
                            else:
                                throttle = -p     # 下 = 後退
                        update_motors()

                    # 左スティック X（左右）
                    elif event.code == ecodes.ABS_X:
                        last_controll_time = time.time()
                        p = scale_axis_evdev(event.value)
                        if p == 0.0:
                            steer = 0.0
                        else:
                            if event.value > center:
                                steer = p        # 右 = 右旋回
                            else:
                                steer = -p       # 左 = 左旋回
                        update_motors()

                # ボタン
                elif event.type == ecodes.EV_KEY and event.value == 1:
                    last_controll_time = time.time()

                    # ×ボタン（非常停止）
                    if event.code in (ecodes.BTN_SOUTH, 304):
                        logger.info("×ボタン → 非常停止")
                        throttle = 0.0
                        steer = 0.0
                        motor_left.stop()
                        motor_right.stop()
                        audio_play("/home/jaxai/Desktop/GLaDOS_escape_02_entry-00.wav")

                    elif event.code in (ecodes.BTN_WEST, 308):
                        logger.info("□ボタン")
                        audio_play("/home/jaxai/Desktop/kane_tarinai.wav")

                    elif event.code in (ecodes.BTN_EAST, 305):
                        logger.info("○ボタン")
                        audio_play("/home/jaxai/Desktop/hatodokei.wav")

                    elif event.code in (ecodes.BTN_NORTH, 307):
                        logger.info("△ボタン")
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
# GUI
# =============================

def read_from_gui():
    global last_controll_time
    if time.time() - last_controll_time < 1:
        return

    try:
        with open("data_from_browser.json") as f:
            d = json.load(f)
        # GUI 側から直接モータ値を上書きするモード
        motor_left.value = float(d["motor_l"])
        motor_right.value = float(d["motor_r"])
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
# 起動
# =============================

logger.info("モーターの動作確認を開始します")
motor_calib()
logger.info("モーターの動作確認が完了しました")

# スレッド起動
threading.Thread(target=start_controller, daemon=True).start()
threading.Thread(
    target=start_gui.start_server,
    kwargs={"logger": logger},  # ← logger を GUI 側に渡す
    daemon=True,
).start()
threading.Thread(target=update_gui, daemon=True).start()
threading.Thread(target=start_camera, daemon=True).start()

logger.info("すべてのセットアップ完了")

# 監視ループ（とりあえず生存確認だけ）
while True:
    time.sleep(10)
