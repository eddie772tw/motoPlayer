# run.py (WebSocket version)

from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # 使用 socketio.run() 來啟動伺服器，以支援 WebSocket
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

# 註：allow_unsafe_werkzeug=True 是新版 Flask-SocketIO 在使用外部排程器時，
#    為了解決 Werkzeug 版本相容性問題而需要加入的參數。
