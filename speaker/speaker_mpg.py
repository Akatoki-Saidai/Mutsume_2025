#-*- cording: utf-8 -*-
# https://www.kobore.net/TPA2006/tpa2006.mm.html

import subprocess

try:
    # セットアップ
    speaker_pin = 12
    subprocess.Popen(f"sudo gpio -g mode {speaker_pin} pwm", shell=True)
    try:
        # print("glados")
        if glados.poll() is None:
            # ファイルパス要変更
            glados = subprocess.Popen("mpg321 door_chime0.mp3", shell=True)
            print(glados.returncode)
        else:
            print("spreaker is running now!")
            print(glados.returncode)
    except subprocess.SubprocessError as sp_e:
        print(f"An error occuerd runnning speaker subprocess(grados): {sp_e}")
except Exception as e:
    print(f"An error occuerd runnning speaker: {e}")


