from pyPS4Controller.controller import Controller
from gpiozero import Motor
from time import sleep

# モータのピン（前に使っていた値）
PIN_AIN1 = 4
PIN_AIN2 = 23
PIN_BIN1 = 13
PIN_BIN2 = 5


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def scale_axis(v: int) -> float:
    """
    pyPS4Controller の L3_* コールバックで渡される value を
    0.0〜1.0 にスケーリングする簡易関数。
    （0〜32767 を 0.0〜1.0 にしてる想定）
    """
    # 念のためマイナスも切る
    v = max(0, v)
    # 仮に最大32767と仮定してスケール
    val = v / 32767.0
    if val < 0.15:  # デッドゾーン
        return 0.0
    return clamp(val, 0.0, 1.0)


class MyController(Controller):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 左右モータ初期化（pigpio は使わずデフォルト）
        self.motor_left = Motor(forward=PIN_AIN2, backward=PIN_AIN1)
        self.motor_right = Motor(forward=PIN_BIN2, backward=PIN_BIN1)

        # 左スティックの状態（-1.0〜1.0）
        self.throttle = 0.0  # 前後（上＋、下−）
        self.steer = 0.0     # 左右（右＋、左−）

        print("Motors initialized, waiting for controller...")

    # ===== 左スティック Y方向 =====
    def on_L3_up(self, value):
        # 上 = 前進（正）
        p = scale_axis(value)
        self.throttle = p
        self.update_motors()
        # print(f"L3 up: {p}")

    def on_L3_down(self, value):
        # 下 = 後退（負）
        p = scale_axis(value)
        self.throttle = -p
        self.update_motors()
        # print(f"L3 down: {-p}")

    def on_L3_y_at_rest(self):
        # 縦方向がセンターに戻った
        self.throttle = 0.0
        self.update_motors()
        # print("L3 Y at rest")

    # ===== 左スティック X方向 =====
    def on_L3_right(self, value):
        # 右 = 右旋回（正）
        p = scale_axis(value)
        self.steer = p
        self.update_motors()
        # print(f"L3 right: {p}")

    def on_L3_left(self, value):
        # 左 = 左旋回（負）
        p = scale_axis(value)
        self.steer = -p
        self.update_motors()
        # print(f"L3 left: {-p}")

    def on_L3_x_at_rest(self):
        # 横方向がセンターに戻った
        self.steer = 0.0
        self.update_motors()
        # print("L3 X at rest")

    # ===== 非常停止（任意のボタン） =====
    def on_x_press(self):
        self.throttle = 0.0
        self.steer = 0.0
        self.motor_left.stop()
        self.motor_right.stop()
        print("X pressed: EMERGENCY STOP")

    # ===== 左スティックの値からモータ出力を計算 =====
    def update_motors(self):
        """
        throttle（前後）と steer（左右）から左右の出力を決める差動制御。
        """
        left_power = self.throttle + self.steer
        right_power = self.throttle - self.steer

        left_power = clamp(left_power, -1.0, 1.0)
        right_power = clamp(right_power, -1.0, 1.0)

        # 両方ほぼゼロなら完全停止
        if abs(left_power) < 0.01 and abs(right_power) < 0.01:
            self.motor_left.stop()
            self.motor_right.stop()
        else:
            self.motor_left.value = left_power
            self.motor_right.value = right_power

        # デバッグ用
        # print(f"motors: L={left_power:.2f}, R={right_power:.2f}")


if __name__ == "__main__":
    controller = MyController(
        interface="/dev/input/js0",
        connecting_using_ds4drv=False,
    )
    print("Listening PS4 controller (left stick)...")
    controller.listen()
