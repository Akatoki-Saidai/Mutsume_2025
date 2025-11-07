# ×ボタン→〇ボタン，〇ボタン→△ボタン，△ボタン→□ボタン，□ボタン→×ボタン
# スピーカー設定をPWM出力可能にしておく(/boot/firmware/config.txtの末尾に"dtoverlay=audremap,pins_12_13"を追加)

from pyPS4Controller.controller import Controller
from gpiozero import Motor
from gpiozero.pins.pigpio import PiGPIOFactory
import subprocess


# 機体ごとに違ったらマズい
PIN_AIN1 = 4
PIN_AIN2 = 23
PIN_BIN1 = 13
PIN_BIN2 = 5


def motor_setup(AIN1, AIN2, BIN1, BIN2):
    dcm_pins = {
        "left_forward": BIN2,
        "left_backward": BIN1,
        "right_forward": AIN1,
        "right_backward": AIN2,
    }

    factory = PiGPIOFactory()
    left = Motor(forward=dcm_pins["left_forward"],
                 backward=dcm_pins["left_backward"],
                 pin_factory=factory)
    right = Motor(forward=dcm_pins["right_forward"],
                  backward=dcm_pins["right_backward"],
                  pin_factory=factory)
    return right, left


def brake(right, left):
    power_r = float(right.value)
    power_l = float(left.value)
    delta_power = 0.15

    for i in range(int(1 / delta_power)):
        if 0<=power_r<=1 and 0<=power_l<=1:
            right.value = power_r
            left.value = power_l
        if power_r > 0:
            power_r -= delta_power
        elif power_r < 0:
            power_r += delta_power
        else:
            pass
        if power_l > 0:
            power_l -= delta_power
        elif power_l < 0:
            power_l += delta_power
        else:
            pass


def transf(raw):
    temp = (raw + 32767) / 65534 / 2
    # Filter values that are too weak for the motors to move
    if abs(temp) < 0.9:
        return 0
    # Return a value between 0.3 and 1.0
    else:
        return round(temp, 1)
    

class MyController(Controller):

    def __init__(self, **kwargs):
        Controller.__init__(self, **kwargs)
        self.motor_right, self.motor_left = motor_setup(PIN_AIN1, PIN_AIN2, PIN_BIN1, PIN_BIN2)
        brake(self.motor_right, self.motor_left)

    # 左スティックの入力値を反映
    def on_R2_press(self, value):
        value = -transf(value)
        parmission_power = 0.25
        delta_power = 0.15

        while (value >= self.motor_right.value + parmission_power) or (value <= self.motor_right.value - parmission_power):
            if -1.0 <= self.motor_right.value + value <= 1.0:
                if value > self.motor_right.value:
                    self.motor_right.value + delta_power
                elif value < self.motor_left.value:
                    self.motor_right.value - delta_power
            else:
                print("over motor value 1 or -1")
                break

        self.motor_right.value = value
        print(f"R3 {value}")
    
    def on_R2_release(self):
        brake(self.motor_right, self.motor_left)
        print("R3 FREE, brake")
    
    def on_L3_press(self, value):
        # Lスティックの入力なんだっけ？
        # 'value' becomes 0 or a float between -1.0 and -0.3
        value = -transf(value)
        parmission_power = 0.25
        delta_power = 0.15

        while (value >= self.motor_left.value + parmission_power) or (value <= self.motor_left.value - parmission_power):
            if -1.0 <= self.motor_left.value + value <= 1.0:
                if value > self.motor_left.value:
                    self.motor_left.value + delta_power
                elif value < self.motor_left.value:
                    self.motor_left.value - delta_power
            else:
                print("over motor value 1 or -1")
                break

        self.motor_left.value = value
        print(f"R3 {value}")
    
    def on_L3_release(self):
        self.motor_left.value = 0
        print("L3 FREE, brake")

    def on_triangle_press(self):
        # 再生終わってるか確認

        try:
            # print("glados")
            if glados.poll() is None:
                # ファイルパス要変更
                glados = subprocess.Popen("aplay --device=hw:1,0 /home/desktop/grados.wav", shell=True)
                print(glados.returncode)
            else:
                print("spreaker is running now!")
                print(glados.returncode)
        except subprocess.SubprocessError as sp_e:
            print(f"An error occuerd runnning speaker subprocess(grados): {sp_e}")

    def on_square_press(self):
        # 再生終わってるか確認

        try:
            # print("glados")
            if stanley.poll() is None:
                # ファイルパス要変更
                stanley = subprocess.Popen("aplay --device=hw:1,0 /home/desktop/stanley.wav", shell=True)
                print(stanley.returncode)
            else:
                print("spreaker is running now!")
                print(stanley.returncode)
        except subprocess.SubprocessError as sp_e:
            print(f"An error occuerd runnning speaker subprocess(stanley): {sp_e}")

    def on_x_press(self):
        # 再生終わってるか確認

        try:
            # print("glados")
            if glenn.poll() is None:
                # ファイルパス要変更
                glenn = subprocess.Popen("aplay --device=hw:1,0 /home/desktop/glenn.wav", shell=True)
                print(glenn.returncode)
            else:
                print("spreaker is running now!")
                print(glenn.returncode)
        except subprocess.SubprocessError as sp_e:
            print(f"An error occuerd runnning speaker subprocess(glenn): {sp_e}")


controller = MyController(interface="/dev/input/js0", connecting_using_ds4drv=False)
controller.listen()
