from picamera2 import Picamera2
import os
print('カメラのセットアップを開始しました')

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
            print('<<エラー>>\nカメラによる画像撮影中にエラーが発生しました: %s')
start_camera()



