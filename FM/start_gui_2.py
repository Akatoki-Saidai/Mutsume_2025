import http.server
from logging import getLogger, NullHandler, Logger
import os
import socket
import socketserver
import subprocess

# ローカルIPを取得
local_ip = ""

# ラズパイ以外で使う場合
# local_ip = socket.gethostbyname_ex(socket.gethostname())[2][-1]

# ラズパイでの IP 取得
str_out_lines = subprocess.Popen(
    "ip addr", stdout=subprocess.PIPE, shell=True
).communicate()[0].decode("ascii", "ignore").splitlines()

for line in str_out_lines:
    if line.startswith("    inet "):
        local_ip = line.split()[1]
        local_ip = (local_ip[0:-3] if local_ip[-3] == '/' else local_ip[0:-2])

HOST, PORT = "", 8000

# 既存の JSON を一度削除
try:
    os.remove("./data_from_browser.json")
    os.remove("./data_to_browser.json")
except Exception:
    pass

# 初期 JSON を生成
try:
    # 受信用
    with open("./data_from_browser.json", "w") as f:
        f.write('{"motor_l": 0, "motor_r": 0, "light": false, "buzzer": false }')

    # 送信用
    with open("./data_to_browser.json", "w") as f:
        f.write(
            '{"motor_l": 0, "motor_r": 0, "light": true, "buzzer": false, '
            '"lat": null, "lon": null, '
            '"grav": [null, null, null], "mag": [null, null, null], '
            '"local_ip": "' + f'{local_ip}:{PORT}' + '"}'
        )
except Exception as e:
    print(f"<<エラー>>\nGUI送受信ファイルへの書き込みに失敗しました: {e}")

# 書き込み権限
subprocess.run("chmod 664 data_from_browser.json", shell=True)
subprocess.run("chmod 664 data_to_browser.json", shell=True)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        file_length = int(self.headers["Content-Length"])
        with open("./data_from_browser.json", "w") as f:
            f.write(self.rfile.read(file_length).decode("utf-8"))

        self.send_response(201, "Created")
        self.end_headers()

        with open("./data_to_browser.json", "r") as f:
            self.wfile.write(f.read().encode("utf-8"))


def start_server(*, logger: Logger = None):
    # ★ ここを修正：logger が None のときは自前で作る ★
    if logger is None:
        logger = getLogger(__name__)
        logger.addHandler(NullHandler())

    while True:
        try:
            with socketserver.TCPServer((HOST, PORT), Handler) as httpd:
                logger.info(
                    "サーバーが稼働しました！  同じネットワーク内のブラウザで http://%s:%d にアクセスしてください",
                    local_ip,
                    PORT,
                )
                httpd.serve_forever()
        except Exception as e:
            logger.error("<<エラー>>\nGUI用のサーバーでエラーが発生しました: %s", e)
