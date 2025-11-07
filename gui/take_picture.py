import os
from picamera2 import Picamera2

# 写真を連続的に取り続けます
# Raspberry Pi 上でのみ動作します
# picamera2 のインストールは↓
# sudo apt update && sudo apt upgrade -y
# sudo apt install -y python3-picamera2

picam2 = Picamera2()
picam2.start()

while True:
    picam2.capture_file('./camera_temp.jpg')
    os.rename("./camera_temp.jpg", "camera.jpg")