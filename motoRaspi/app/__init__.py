# motoRaspi/app/__init__.py (v6.3 - 穩定版)
#
# 版本更新說明:
# - [優化] 調整了 atexit cleanup 函式，使用 asyncio.run() 來執行非同步的 disconnect，
#   使其更健壯且能避免潛在的事件循環衝突。
# - [優化] 在 cleanup 函式中，對 dmx_controller 的連線檢查更加安全。

import logging
import atexit
import asyncio
from flask import Flask
from flask_socketio import SocketIO
from flask_apscheduler import APScheduler
from DMX import DMXController
import config

# --- 全域變數 ---
# 為了讓背景任務和主應用都能存取，我們將實例宣告為全域變數
obd_sensor = None
dmx_controller = None

# --- 設定日誌 ---
logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('apscheduler').setLevel(logging.ERROR)

# --- 初始化 Flask 擴充 ---
socketio = SocketIO(cors_allowed_origins="*")
apscheduler = APScheduler()

def create_app():
    from . import tasks
    from . import state
    global obd_sensor, dmx_controller
    app = Flask(__name__)
    app.config.from_object(config.Config)

    # --- 階段一: 初始化感測器與控制器 ---
    
    # 初始化 DMX 控制器 (非同步)
    if config.DMX_MAC_ADDRESS and config.DMX_MAC_ADDRESS != "XX:XX:XX:XX:XX:XX":
        dmx_controller = DMXController(config.DMX_MAC_ADDRESS)
        logger.info(f"DMX 控制器 {config.DMX_MAC_ADDRESS} 初始化完畢。")
    else:
        dmx_controller = None
        logger.warning("DMX 控制器未設定，相關功能將停用。")
    
    # 初始化 OBD 感測器 (同步)
    if config.OBD_MODE == 'REAL':
        try:
            from real_obd import RealOBD
            logger.info(f"正在嘗試與 OBD 診斷器 ({config.OBD_DEVICE_ADDRESS}) 建立連線...")
            obd_sensor = RealOBD(mac_address=config.OBD_DEVICE_ADDRESS)
            if not obd_sensor.connect():
                logger.warning("無法連接到 OBD 感測器，將退回使用模擬器。")
                from mock_obd import MockOBD
                obd_sensor = MockOBD()
        except Exception as e:
            logger.error(f"初始化真實 OBD 時發生錯誤: {e}，將退回使用模擬器。")
            from mock_obd import MockOBD
            obd_sensor = MockOBD()
    else:
        from mock_obd import MockOBD
        logger.info("正在使用模擬 OBD 模式。")
        obd_sensor = MockOBD()

    # --- 階段二: 設定背景排程任務 ---
    socketio.init_app(app)
    
    if not apscheduler.running:
        apscheduler.init_app(app)
        apscheduler.add_job(id='FetchOBDJob', func=tasks.fetch_obd_data, args=[obd_sensor], trigger='interval', seconds=config.OBD_FETCH_INTERVAL_MS / 1000)
        apscheduler.add_job(id='FetchNodeMCUJob', func=tasks.fetch_nodemcu_data, trigger='interval', seconds=config.NODEMCU_FETCH_INTERVAL_S)
        apscheduler.add_job(id='PushWebSocketJob', func=tasks.push_data_via_websocket, trigger='interval', seconds=config.WEBSOCKET_PUSH_INTERVAL_MS / 1000)
        apscheduler.add_job(id='WriteDBJob', func=tasks.write_buffer_to_db, trigger='interval', seconds=config.DB_WRITE_INTERVAL_S)
        apscheduler.start()
        logger.info("多執行緒背景服務已啟動。")

    # --- 階段三: 註冊路由與清理函式 ---
    from . import routes
    app.register_blueprint(routes.bp)

    # 定義應用程式關閉時的清理工作
    def cleanup():
        if obd_sensor and obd_sensor.is_connected:
            logger.info("App cleanup: 正在中斷與 OBD 感測器的連線...")
            obd_sensor.disconnect()
        
        if dmx_controller and dmx_controller.is_connected:
            logger.info("App cleanup: 正在中斷與 DMX 控制器的連線...")
            try:
                # 使用 asyncio.run() 是在同步函式中執行非同步程式碼最安全的方式
                asyncio.run(dmx_controller.disconnect())
            except Exception as e:
                logger.error(f"關閉 DMX 連線時發生錯誤: {e}")

    atexit.register(cleanup)
    
    return app
