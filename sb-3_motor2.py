from time import sleep
from pyPS4Controller.controller import Controller
from gpiozero import Motor
from gpiozero.pins.pigpio import PiGPIOFactory


def setup(AIN1, AIN2, BIN1, BIN2):
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


PIN_AIN1 = 4
PIN_AIN2 = 23
PIN_BIN1 = 13
PIN_BIN2 = 5
motor_right, motor_left = setup(PIN_AIN1, PIN_AIN2, PIN_BIN1, PIN_BIN2)


def transf(raw):
    temp = (raw + 32767) / 65534 / 2
    # Filter values that are too weak for the motors to move
    if abs(temp) < 0.9:
        return 0
    # Return a value between 0.3 and 1.0
    else:
        return round(temp, 1)


def transf1(raw):
    temp = (abs(raw) + 32767) / 65534 / 2
    # Filter values that are too weak for the motors to move
    if abs(temp) < 0.9:
        return 0
    # Return a value between 0.3 and 1.0
    else:
        return round(temp, 1)


class MyController(Controller):

    def __init__(self, motor_left, motor_right, **kwargs):
        Controller.__init__(self, **kwargs)
        self.motor_left = motor_left
        self.motor_right = motor_right
    
    def on_R1_press(self):
        self.motor_right.value = 0.2

    def on_R1_release(self):
        self.motor_right.value = 0
    
    def on_L1_press(self):
        self.motor_right.value = 0.2

    def on_L1_release(self):
        self.motor_left.value = 0

    def on_circle_press(self):
        self.motor_right.value = -0.2
        self.motor_left.value = -0.2

    def on_circle_release(self):
        self.motor_right.value = 0
        self.motor_left.value = 0



controller = MyController(motor_left=motor_left, motor_right=motor_right, interface="/dev/input/js0", connecting_using_ds4drv=False)
controller.listen()
