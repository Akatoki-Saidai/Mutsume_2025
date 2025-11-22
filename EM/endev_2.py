import json
from logging import getLogger, StreamHandler, Formatter, Logger, DEBUG, INFO, WARNING, ERROR, CRITICAL
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import threading
import time

os.chdir(os.path.dirname(__file__))  # このプログラムファイルの場所を，カレントディレクトリに設定

##### ログに関する設定 #####
try:
    os.remove('print.txt')
    os.remove('fm.log')
except Exception as e:
    pass
sys.stdout = open('print.txt', 'w')  # 不要なログが大量に出てくるので，コンソールに出力しない．(あまり良くないことかも)

logger = getLogger(__name__)
logger.setLevel(DEBUG)
logger.propagate = False

s_handler = StreamHandler()
s_handler.setLevel(INFO)
logger.addHandler(s_handler)

tsv_format = Formatter('%(asctime)s.%(msecs)d+09:00\t%(name)s\t%(filename)s\t%(lineno)d\t%(funcName)s\t%(levelname)s\t%(message)s', '%Y-%m-%dT%H:%M:%S')
f_handler = RotatingFileHandler('fm.log', maxBytes=100*1000)
f_handler.setLevel(DEBUG)
f_handler.setFormatter(tsv_format)
logger.addHandler(f_handler)
#######################


logger.info('セットアップを開始します')

logger.info('実行環境を確認しています')
if sys.prefix == sys.base_prefix:
    logger.warning('<<警告>>\n仮想環境で実行していない可能性があります．仮想環境でない場合は次のコマンドを実行し再度このプログラムを起動してください．source fm_env/bin/activate')
    time.sleep(10)
logger.info('実行環境の確認が完了しました')

logger.info('コントローラと無線接続を行います')
logger.info('PS4コントローラーのPSボタンとSHAREボタンを同時に，青いランプが光るまで長押ししてください')
# subprocess.Popen('sudo ds4drv', shell=True, stdout=subprocess.DEVNULL)
# time.sleep(20)


logger.info('ライブラリをインポートしています')
from gpiozero import Motor
from gpiozero.pins.pigpio import PiGPIOFactory
from picamera2 import Picamera2
import evdev
from evdev import InputDevice, categorize, ecodes
logger.info('ライブラリのインポートが完了しました')

logger.info('別のPythonファイルを読み込んでいます')
import start_gui
logger.info('別のPythonファイルの読み込みが完了しました')


##### モーター #####
logger.info('モーターのセットアップを開始します')

# ピン番号要確認
PIN_R1 = 2
PIN_R2 = 3
PIN_L1 = 17
PIN_L2 = 27
motor_right = Motor(forward=PIN_R1, backward=PIN_R2, pin_factory=PiGPIOFactory())
motor_left  = Motor(forward=PIN_L1, backward=PIN_L2, pin_factory=PiGPIOFactory())

# 左スティックの状態（-1.0〜1.0）
throttle = 0.0  # 前後（上＋、下−）
steer = 0.0     # 左右（右＋、左−）


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def scale_axis_evdev(v: int) -> float:
    """
    evdev の ABS_*（0〜255, 中心 ~127.5）を 0.0〜1.0 に正規化。
    絶対値だけを返す（向きは呼び出し側で決める）。
    """
    center = 127.5
    val = abs(v - center) / center  # 0.0〜1.0
    if val < 0.15:
        return 0.0  # デッドゾーン
    return clamp(val, 0.0, 1.0)


def update_motors():
    """
    throttle（前後）と steer（左右）から左右の出力を決める差動制御。
    下の pyPS4Controller 版と同じロジック。
    """
    global throttle, steer

    left_power = throttle + steer
    right_power = throttle - steer

    left_power = clamp(left_power, -1.0, 1.0)
    right_power = clamp(right_power, -1.0, 1.0)

    # 両方ほぼゼロなら完全停止
    if abs(left_power) < 0.01 and abs(right_power) < 0.01:
        motor_left.stop()
        motor_right.stop()
    else:
        motor_left.value = left_power
        motor_right.value = right_power

    logger.debug('motors updated: L=%.2f, R=%.2f', left_power, right_power)


def motor_calib():
    power = 0
    delta_power = 0.2

    logger.info("右モーターのテストを行います")
    for i in range(int(1 / delta_power)):
        if 0 <= power <= 1:
            motor_right.value = power
            power += delta_power
    motor_right.value = 1
    time.sleep(0.5)

    for i in range((int(1 / delta_power)) * 2):
        if -1 <= power <= 1:
            motor_right.value = power
            power -= delta_power
    motor_right.value = -1
    time.sleep(0.5)

    for i in range(int(1 / delta_power)):
        if -1 <= power <= 0:
            motor_right.value = power
            power += delta_power
    motor_right.value = 0
    time.sleep(0.5)

    logger.info("左モーターのテストを行います")
    for i in range(int(1 / delta_power)):
        if 0 <= power <= 1:
            motor_left.value = power
            power += delta_power
    motor_left.value = 1
    time.sleep(0.5)

    for i in range((int(1 / delta_power)) * 2):
        if -1 <= power <= 1:
            motor_left.value = power
            power -= delta_power
    motor_left.value = -1
    time.sleep(0.5)

    for i in range(int(1 / delta_power)):
        if -1 <= power <= 0:
            motor_left.value = power
            power += delta_power
    motor_left.value = 0
    time.sleep(0.5)

logger.info('モーターのセットアップが完了しました')

##### スピーカー #####

logger.info('スピーカーのセットアップを開始しました')

proces_aplay = None
# .poll()は終了していなかったらNone，終了していたらそのステータスを返す．
def audio_play(audio_path):
    global proces_aplay
    logger.debug('audio_path: %s', audio_path)
    if (proces_aplay is None or proces_aplay.poll() is not None):
        proces_aplay = subprocess.Popen(f"aplay --device=hw:1,0 {audio_path}", shell=True)
        logger.info("音楽の再生中です")
    else:
        logger.info("音楽がすでに再生中のためキャンセルします")

logger.info('スピーカーのセットアップが完了しました')


###### コントローラ #####
logger.info('コントローラーによる制御システムのセットアップを開始しました')

last_controll_time = time.time()


def connect():
    logger.warning('<<警告>>\nコントローラーと接続しました')


def disconnect():
    logger.warning('<<警告>>\nコントローラーとの接続が切れました')


def start_controller():
    global last_controll_time, throttle, steer

    center = 127.5

    while True:
        device = None
        logger.info("コントローラーデバイスを探しています... (PSボタンを押して接続してください)")

        # デバイス探索
        while device is None:
            try:
                devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
                for dev in devices:
                    if 'Wireless Controller' in dev.name:
                        device = dev
                        break
            except Exception:
                pass

            if device is None:
                time.sleep(2)

        connect()
        logger.info(f"Connected to {device.name} at {device.path}")

        try:
            # デバイスを占有
            device.grab()

            for event in device.read_loop():
                if event.type == ecodes.EV_ABS:
                    # 左スティック Y（前後）
                    if event.code == ecodes.ABS_Y:
                        last_controll_time = time.time()
                        p = scale_axis_evdev(event.value)

                        if p == 0.0:
                            throttle = 0.0
                        else:
                            if event.value < center:
                                # 上 = 前進（正）
                                throttle = p
                            else:
                                # 下 = 後退（負）
                                throttle = -p

                        update_motors()

                    # 左スティック X（左右）
                    elif event.code == ecodes.ABS_X:
                        last_controll_time = time.time()
                        p = scale_axis_evdev(event.value)

                        if p == 0.0:
                            steer = 0.0
                        else:
                            if event.value > center:
                                # 右 = 右旋回（正）
                                steer = p
                            else:
                                # 左 = 左旋回（負）
                                steer = -p

                        update_motors()

                elif event.type == ecodes.EV_KEY:
                    if event.value == 1:
                        last_controll_time = time.time()
                        # ボタンマッピング (標準ドライバの場合)
                        if event.code == ecodes.BTN_SOUTH or event.code == 304:  # X
                            logger.info('×ボタンが押されました')
                            # 非常停止
                            throttle = 0.0
                            steer = 0.0
                            motor_left.stop()
                            motor_right.stop()
                            audio_play("/home/jaxai/Desktop/GLaDOS_escape_02_entry-00.wav")

                        elif event.code == ecodes.BTN_WEST or event.code == 308:  # Square
                            logger.info('□ボタンが押されました')
                            audio_play("/home/jaxai/Desktop/kane_tarinai.wav")

                        elif event.code == ecodes.BTN_EAST or event.code == 305:  # Circle
                            logger.info('○ボタンが押されました')
                            audio_play("/home/jaxai/Desktop/hatodokei.wav")

                        elif event.code == ecodes.BTN_NORTH or event.code == 307:  # Triangle
                            logger.info('△ボタンが押されました')
                            audio_play("/home/jaxai/Desktop/otoko_ou!.wav")

        except OSError:
            disconnect()
            time.sleep(1)
        except Exception as e:
            logger.error(f'<<エラー>>\nコントローラー制御エラー: {e}')
            disconnect()
            time.sleep(1)
        finally:
            try:
                device.ungrab()
            except Exception:
                pass

logger.info('コントローラーによる制御システムのセットアップが完了しました')


##### GUI #####
logger.info('GUIによる制御システムのセットアップを開始しました')

def read_from_gui():
    global last_controll_time
    if time.time() - last_controll_time < 1:
        return

    data_from_browser = {}
    with open('data_from_browser.json', 'r') as f:
        data_from_browser = json.load(f)
    logger.debug('data_from_browser: %s', data_from_browser)

    motor_right.value = float(data_from_browser['motor_r'])
    motor_left.value = float(data_from_browser['motor_l'])
    if bool(data_from_browser['light']):
        # high_power_led.on()
        pass
    else:
        # high_power_led.off()
        pass
    if bool(data_from_browser['buzzer']):
        audio_play('/home/jaxai/Desktop/GLaDOS_escape_02_entry-00.wav')


def write_to_gui():
    data_to_browser = {}
    with open('data_to_browser.json', 'r') as f:
        data_to_browser = json.load(f)

    with open('data_to_browser.json', 'w') as f:
        data_to_browser['motor_r'] = motor_right.value
        data_to_browser['motor_l'] = motor_left.value
        # data_to_browser['light'] = bool(high_power_led.value)
        data_to_browser['light'] = False
        data_to_browser['buzzer'] = False
        f.write(json.dumps(data_to_browser))


def update_gui():
    while True:
        try:
            read_from_gui()
            write_to_gui()
            time.sleep(0.8)
        except Exception as e:
            logger.error('<<エラー>>\nGUIによる制御中にエラーが発生しました: %s', e)

logger.info('GUIによる制御システムのセットアップが完了しました')


##### カメラ #####
logger.info('カメラのセットアップを開始しました')

picam2 = Picamera2()
picam_config = picam2.create_preview_configuration()
# picam_config["transform"] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(picam_config)
picam2.start()


def start_camera():
    while True:
        try:
            picam2.capture_file('camera_temp.jpg')
            os.rename("camera_temp.jpg", "camera.jpg")
            time.sleep(0.1)
        except Exception as e:
            logger.error('<<エラー>>\nカメラによる画像撮影中にエラーが発生しました: %s', e)

logger.info('カメラのセットアップが完了しました')


##### モーターの動作確認 #####
logger.info('モーターの動作確認を開始します')
motor_calib()
logger.info('モーターの動作確認が完了しました')


##### 平行処理(daemon)を開始 #####
logger.info('並行処理による同時実行システムの定義を行います')

# コントローラーを起動
controller_thread = threading.Thread(target=start_controller, daemon=True)

# GUI用のサーバーを起動
server_thread = threading.Thread(target=start_gui.start_server, daemon=True)

# GUIのデータを読み込み・書き込み
gui_thread = threading.Thread(target=update_gui, daemon=True)

# カメラで撮影開始
camera_thread = threading.Thread(target=start_camera, daemon=True)

logger.info('コントローラーを起動します')
controller_thread.start()

logger.info('GUI用のサーバーを起動します')
server_thread.start()

logger.info('GUIによる制御システムを起動します')
gui_thread.start()

logger.info('カメラによる連続撮影を開始します')
camera_thread.start()

logger.info('セットアップが完了しました')

first_thread_count = threading.active_count()
while threading.active_count() != 1:
    if first_thread_count == threading.active_count():
        logger.info('正常に実行されています')
    else:
        logger.error('<<エラー>>\nプログラムの一部が停止しています')
    time.sleep(10)
