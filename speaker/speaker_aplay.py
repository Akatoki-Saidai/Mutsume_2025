#-*- cording: utf-8 -*-
# スピーカー設定をPWM出力可能にしておく(/boot/firmware/config.txtの末尾に"dtoverlay=audremap,pins_12_13"を追加)

import subprocess

try:
    try:
        # print("glados")
        if glados.poll() is None:
            # ファイルパス要変更
            glados = subprocess.Popen("aplay --device=hw:1,0 /home/jaxai/Desktop/grados.wav", shell=True)
            print(glados.returncode)
        else:
            print("spreaker is running now!")
            print(glados.returncode)
    except subprocess.SubprocessError as sp_e:
        print(f"An error occuerd runnning speaker subprocess(grados): {sp_e}")
except Exception as e:
    print(f"An error occuerd runnning speaker: {e}")


