# むつめ祭2024にて機体を遠隔操作するためのプログラムです

# 必ず仮想環境で実行してください
# 仮想環境の作成：sudo python -m venv fm_env --system-site-packages
# 仮想環境に入る：source fm_env/bin/activate

# スピーカー設定をPWM出力可能にしておく(/boot/firmware/config.txtの末尾に"dtoverlay=audremap,pins_18_19"を追加)

import json
from logging import getLogger, StreamHandler, Formatter, Logger, DEBUG, INFO, WARNING, ERROR, CRITICAL
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import threading
import time

# 本プログラムではむつめ祭来場者にログを見せる可能性や
# プログラムに慣れない人がプログラムを実行する可能性を考慮し
# ログの一部を日本語で出力しています．良い子はマネしないでね

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
subprocess.Popen('sudo ds4drv', shell=True, stdout=subprocess.DEVNULL)
time.sleep(20)


logger.info('ライブラリをインポートしています')
# from gpiozero import LED
from gpiozero import Motor
from gpiozero.pins.pigpio import PiGPIOFactory
import libcamera
from picamera2 import Picamera2
from pyPS4Controller.controller import Controller
logger.info('ライブラリのインポートが完了しました')

logger.info('別のPythonファイルを読み込んでいます')
import start_gui
logger.info('別のPythonファイルの読み込みが完了しました')


##### モーター #####
logger.info('モーターのセットアップを開始します')

PIN_R1 = 4
PIN_R2 = 23
PIN_L1 = 26
PIN_L2 = 5
motor_right = Motor(forward = PIN_R1, backward = PIN_R2, pin_factory = PiGPIOFactory())
motor_left  = Motor(forward = PIN_L1, backward = PIN_L2, pin_factory = PiGPIOFactory())

def motor_calib():
    power = 0
    delta_power = 0.2

    logger.info("右モーターのテストを行います")
    for i in range(int(1 / delta_power)):
        if 0<=power<=1:
            motor_right.value = power
            power += delta_power
    motor_right.value = 1
    time.sleep(0.5)

    for i in range((int(1 / delta_power))*2):
        if -1<=power<=1:
            motor_right.value = power
            power -= delta_power
    motor_right.value = -1
    time.sleep(0.5)

    for i in range(int(1 / delta_power)):
        if -1<=power<=0:
            motor_right.value = power
            power += delta_power
    motor_right.value = 0
    time.sleep(0.5)

    logger.info("左モーターのテストを行います")
    for i in range(int(1 / delta_power)):
        if 0<=power<=1:
            motor_left.value = power
            power += delta_power
    motor_left.value = 1
    time.sleep(0.5)

    for i in range((int(1 / delta_power))*2):
        if -1<=power<=1:
            motor_left.value = power
            power -= delta_power
    motor_left.value = -1
    time.sleep(0.5)

    for i in range(int(1 / delta_power)):
        if -1<=power<=0:
            motor_left.value = power
            power += delta_power
    motor_left.value = 0
    time.sleep(0.5)

logger.info('モーターのセットアップが完了しました')


##### ライト #####
logger.info('ライトのセットアップを開始します')

# high_power_led = LED(17)
# high_power_led.off()
logger.warning('<<警告>>\n今回のむつめ祭ではライトの使用を取りやめました')

logger.info('ライトのセットアップが完了しました')


##### スピーカー #####

logger.info('スピーカーのセットアップを開始しました')
class C():
    def poll(self):
        return 0  # まだ開始していない

proces_aplay = C()
# .poll()は終了していなかったらNone，終了していたらそのステータスを返す．
def audio_play(audio_path):
    global proces_aplay
    logger.debug('audio_path: %s', audio_path)
    if (proces_aplay.poll() != None):
        proces_aplay = subprocess.Popen(f"aplay --device=hw:1,0 {audio_path}", shell=True)
        # proces_aplay.returncode
        logger.info("音楽の再生中です")
    else:
        logger.info("音楽がすでに再生中のためキャンセルします")

logger.info('スピーカーのセットアップが完了しました')


###### コントローラ #####
logger.info('コントローラーによる制御システムのセットアップを開始しました')

last_controll_time = time.time()

def transf(raw):
    temp = raw / (1 << 15)
    # Filter values that are too weak for the motors to move
    if abs(temp) < 0.05:
        return 0
    # Return a value between 0.2 and 1.0
    else:
        return round(temp, 2)
    
last_r2_release_time = time.time()

# 右スティック前：R2_press　負
# 右スティック後：R2_press　正
# 左スティック前：L3_up　負
# 左スティック後：L3_down　正
# ×ボタン→〇ボタン，〇ボタン→△ボタン，△ボタン→□ボタン，□ボタン→×ボタン
class MyController(Controller):
    def __init__(self, **kwargs):
        Controller.__init__(self, **kwargs)
    
    def on_R2_press(self, value):
        global last_controll_time
        last_controll_time = time.time()
        logger.debug('R2_press value: %f', value)
        # 右モーター前進/後退
        power = -transf(value)
        motor_right.value = power
        logger.info('右スティックの操作中. 右モーター出力: %f', motor_right.value)

    def on_R2_release(self):
        # global last_controll_time
        # last_controll_time = time.time()
        # 右モーター停止
        if time.time() - last_r2_release_time < 0.2:
            motor_right.value = 0
            logger.info('右スティックが無操作. 右モーター出力: %f', motor_right.value)
        last_r2_release_time = time.time()

    def on_L3_up(self, value):
        global last_controll_time
        last_controll_time = time.time()
        logger.debug('L3_up value: %f', value)
        # 左モーター前進
        power = -transf(value)
        motor_left.value = power
        logger.info('左スティックの操作中. 左モーター出力: %f', motor_left.value)

    def on_L3_down(self, value):
        global last_controll_time
        last_controll_time = time.time()
        logger.debug('L3_down value: %f', value)
        # 左モーター後退
        power = -transf(value)
        motor_left.value = power
        logger.info('左スティックの操作中. 左モーター出力: %f', motor_left.value)

    def on_L3_y_at_rest(self):
        # global last_controll_time
        # last_controll_time = time.time()
        # 左モーター停止
        motor_left.value = 0
        logger.info('左スティックが無操作. 左モーター出力: %f', motor_left.value)

    def on_x_press(self):
        logger.info('□ボタンが押されました')
        global last_controll_time
        last_controll_time = time.time()
        # 音楽を再生
        audio_play("/home/jaxai/Desktop/GLaDOS_escape_02_entry-00.wav")
    
    def on_square_press(self):
        logger.info('△ボタンが押されました')
        global last_controll_time
        last_controll_time = time.time()
        audio_play("/home/jaxai/Desktop/kane_tarinai.wav")
    
    def on_circle_press(self):
        logger.info('×ボタンが押されました')
        global last_controll_time
        last_controll_time = time.time()
        audio_play("/home/jaxai/Desktop/hatodokei.wav")

    def on_triangle_press(self):
        logger.info('○ボタンが押されました')
        global last_controll_time
        last_controll_time = time.time()
        audio_play("/home/jaxai/Desktop/otoko_ou!.wav")


def connect():
    logger.warning('<<警告>>\nコントローラーと接続しました')

def disconnect():
    logger.warning('<<警告>>\nコントローラーとの接続が切れました')

def start_controller():
    while True:
        try:
            controller = MyController(interface="/dev/input/js0", connecting_using_ds4drv=False)
            controller.listen(on_connect=connect, on_disconnect=disconnect)
        except Exception as e:
            logger.error('<<エラー>>\nコントローラーによる制御でエラーが発生しました: %s', e)

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
picam_config["transform"] = libcamera.Transform(hflip=1, vflip=1)
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


##### 平行処理を開始 #####
logger.info('並行処理による同時実行システムの定義を行います')

# コントローラーを起動
controller_thread = threading.Thread(target=start_controller)

# GUI用のサーバーを起動
server_thread = threading.Thread(target=start_gui.start_server)

# GUIのデータを読み込み・書き込み
gui_thread = threading.Thread(target=update_gui)

# カメラで撮影開始
camera_thread = threading.Thread(target=start_camera)

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

### 参考にしたサイト
# thread関連
# https://qiita.com/kaitolucifer/items/e4ace07bd8e112388c75
# コントローラーの接続
# https://hellobreak.net/raspberry-pi-ps4-controller-0326/
# ログの記録
# https://qiita.com/smats-rd/items/c5f4345aca3a452041c7