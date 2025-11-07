import time
from gpiozero import LED

while True:
    try:
        high_power_led = LED(17)
        high_power_led.off()
    except Exception as e:
        print(f"An error occured in setting LED: {e}")
        
    input("LED on?")

    try:
        high_power_led.on()
        time.sleep(1)
    
    except Exception as e:
        print(f"An error occured in lightning LED: {e}")

    print("LED off")





    