#-*- cording: utf-8 -*-

import wave
import pyaudio

try:
    # チャンク数を指定
    CHUNK = 16
    filename = "ファイル名.wav"

    grados = wave.open(filename, 'rb')

    # PyAudioのインスタンスを生成
    speaker = pyaudio.PyAudio()

    # Streamを生成
    stream = speaker.open(format=speaker.get_format_from_width(grados.getsampwidth()),
                    channels=grados.getnchannels(),
                    rate=grados.getframerate(),
                    output=True)

    """
    format: ストリームを読み書きする際のデータ型
    channels: モノラルだと1、ステレオだと2、それ以外の数字は入らない
    rate: サンプル周波数
    output: 出力モード
    """

    # データを1度に16個読み取る
    data = grados.readframes(CHUNK)

    # 実行
    while data != '':
        # ストリームへの書き込み
        stream.write(data)
        # 再度1024個読み取る
        data = grados.readframes(CHUNK)

    # ファイルが終わったら終了処理
    stream.stop_stream()
    stream.close()

    speaker.terminate()

except Exception as e:
    print(f"An error occuerd runnning speaker: {e}")
