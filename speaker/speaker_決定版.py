import subprocess

# 事前に None で初期化
glados = None

try:
    if glados is None or glados.poll() is not None:
        # プロセスが存在しないか、すでに終了している場合 → 新しく再生
        glados = subprocess.Popen(
            "aplay --device=hw:1,0 /home/jaxai/Desktop/grados.wav",
            shell=True
        )
        print("Started playing grados.wav")
    else:
        # まだ再生中ならスキップ
        print("Speaker is running now!")
except subprocess.SubprocessError as sp_e:
    print(f"An error occurred running speaker subprocess (grados): {sp_e}")
except Exception as e:
    print(f"An error occurred running speaker: {e}")
