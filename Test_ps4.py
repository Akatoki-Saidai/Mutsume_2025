# むつめ祭2024にて機体を遠隔操作するためのプログラムです

# ×ボタン→〇ボタン，〇ボタン→△ボタン，△ボタン→□ボタン，□ボタン→×ボタン
# スピーカー設定をPWM出力可能にしておく(/boot/firmware/config.txtの末尾に"dtoverlay=audremap,pins_12_13"を追加)

import os
import json
import subprocess
# import threading
import time

from gpiozero import LED
from gpiozero import Motor
from gpiozero.pins.pigpio import PiGPIOFactory
from picamera2 import Picamera2
from pyPS4Controller.controller import Controller

# import start_gui


##### モーター #####
# PIN_R1 = 4
# PIN_R2 = 23
# PIN_L1 = 13
# PIN_L2 = 5
# motor_right = Motor(forward = PIN_R1, backward = PIN_R2, pin_factory = PiGPIOFactory)
# motor_left  = Motor(forward = PIN_L1, backward = PIN_L2, pin_factory = PiGPIOFactory)


# ##### ライト #####
# high_power_led = LED(17)
# high_power_led.off()


##### スピーカー #####
class C():
    def poll():
        return None
proces_aplay = C()
def audio_play():
    global proces_aplay
    if proces_aplay.poll() is None:
        proces_aplay = subprocess.Popen("aplay --device=hw:1,0 ファイル名.wav", shell=True)
        proces_aplay.returncode


###### コントローラ #####

last_controll_time = time.time()  # 実質的なグローバル変数

def transf(raw):
    # temp = raw / 32767
    temp = raw / (1 << 15)
    # Filter values that are too weak for the motors to move
    if abs(temp) < 0.2:  # <-- 0.3の間違いでは?
        return 0
    # Return a value between 0.2 and 1.0
    else:
        return round(temp, 2)

class MyController(Controller):
    def __init__(self, **kwargs):
        Controller.__init__(self, **kwargs)
    
    def on_R2_press(self, value):
        print(f'ctrl,R2,press,{value}')
        global last_controll_time
        last_controll_time = time.time()
        # motor_right.value = -transf(value)
        print(-transf(value))
    
    def on_R3_down(self, value):
        print(f'ctrl,R3,down,{value}')
        global last_controll_time
        last_controll_time = time.time()
        # motor_right.value = -transf(value)
        print(-transf(value))
    
    def on_L3_up(self, value):
        print(f'ctrl,L3,up,{value}')
        global last_controll_time
        last_controll_time = time.time()
        # motor_left.value = -transf(value)
        print(-transf(value))
    
    def on_L3_down(self, value):
        print(f'ctrl,L3,down,{value}')
        global last_controll_time
        last_controll_time = time.time()
        # motor_left.value = -transf(value)
        print(-transf(value))
    
    def on_x_press(self):
        print('ctrl,x,press')
        global last_controll_time
        last_controll_time = time.time()
        audio_play()
    
    def on_square_press(self):
        print('ctrl,square,press')
        global last_controll_time
        last_controll_time = time.time()
        # high_power_led.on()

    def on_square_release(self):
        print('ctrl,square,release')
        global last_controll_time
        last_controll_time = time.time()
        # high_power_led.off()

def connect():
    print('ctrl,connect')

def disconnect():
    print('ctrl,disconnect')

def start_controller():
    controller = MyController(interface="/dev/input/js0", connecting_using_ds4drv=False)
    controller.listen(on_connect=connect, on_disconnect=disconnect)


##### GUI #####

# def read_from_gui():
#     global last_controll_time
#     if time.time() - last_controll_time < 1:
#         return
    
#     data_from_browser = {}
#     with open('data_from_browser', 'r') as f:
#         data_from_browser = json.load(f)
    
#     motor_right.value = float(data_from_browser['motor_r'])
#     motor_left.value = float(data_from_browser['motor_l'])
#     if bool(data_from_browser['light']):
#         high_power_led.on()
#     else:
#         high_power_led.off()
#     if bool(data_from_browser['buzzer']):
#         audio_play()
#     print(f'gui,{data_from_browser['motor_l']},{data_from_browser['motor_r']},{data_from_browser['light']},{data_from_browser['buzzer']}')

# def write_to_gui():
#     data_to_browser = {}
#     data_to_browser['motor_r'] = motor_right.value
#     data_to_browser['motor_l'] = motor_left.value
#     data_to_browser['light'] = high_power_led.value
#     data_to_browser['buzzer'] = False if (proces_aplay.poll() is None) else True
#     s = json.dumps(data_to_browser)
#     with open('data_to_browser', 'w') as f:
#         f.write(s)

# def update_gui():
#     while True:
#         read_from_gui()
#         write_to_gui()
#         time.sleep(0.1)


# ##### カメラ #####

# picam2 = Picamera2()
# picam2.start()

# def start_camera():
#     while True:
#         picam2.capture_file('camera_temp.jpg')
#         os.rename("camera_temp.jpg", "camera.jpg")


# ##### 平行処理を開始 #####

# コントローラーを起動
start_controller()

# # GUI用のサーバーを起動
# server_thread = threading.Thread(target=start_gui.start_server)

# # GUIのデータを読み込み・書き込み
# gui_thread = threading.Thread(target=update_gui)

# # カメラで撮影開始
# camera_thread = threading.Thread(target=start_camera)


# while threading.active_count() != 1:
#     print(f'main,{threading.active_count()}')
#     time.sleep(10)

# 参考にしたサイト
# https://qiita.com/kaitolucifer/items/e4ace07bd8e112388c75
    
