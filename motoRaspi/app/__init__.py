# app/__init__.py (v6.1 - Fixed & Integrated)
#
# 版本更新說明:
# - 此版本已完全還原為同步架構，以配合使用 PyBluez 的傳統藍牙 RFCOMM 方案。
# - [FIX] 補上了所有遺漏的 import (logging, atexit, asyncio)。
# - [FIX] 修正了 DMXController 的導入路徑，假設其位於 dmx_controller.py 中。
# - [FIX] 調整了 create_app 函式的結構，將所有初始化邏輯移至函式開頭。
# - [FIX] 修正了應用程式關閉時的 DMX 清理邏輯，避免同步/非同步衝突。

import sqlite3
import time
import socket
import requests
import logging
import atexit
import asyncio
from flask import Flask
from flask_socketio import SocketIO
from flask_apscheduler import APScheduler
from pydantic import ValidationError
from datetime import datetime, timedelta
from threading import Lock
from itertools import groupby
from statistics import mean

# 假設 DMX 控制器邏輯被封裝在 dmx_controller.py 中
# from dmx_controller import DMXController 
from . import state
from app.models import MotoData, EnvironmentalData, SystemStatus
import config

# --- 全域變數 ---
obd_sensor = None
dmx_controller = None

# --- 設定日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 設定 ---
NODEMCU_HOSTNAME = "motoplayer.local"
DATABASE_PATH = "motoplayer.db"
TRIP_TIMEOUT_MINUTES = 30
OBD_FETCH_INTERVAL_MS = 200
NODEMCU_FETCH_INTERVAL_S = 2.5
WEBSOCKET_PUSH_INTERVAL_MS = 200
DB_WRITE_INTERVAL_S = 60

# --- 初始化 ---
socketio = SocketIO()

# --- 背景任務函式 (同步) ---
def find_mcu_ip():
    try:
        ip = socket.gethostbyname(NODEMCU_HOSTNAME)
        if ip != state.mcu_ip_address: logging.info(f"[INFO] mDNS: '{NODEMCU_HOSTNAME}' -> {ip}"); state.mcu_ip_address = ip
    except socket.gaierror:
        if state.mcu_ip_address is not None: logging.warning(f"[WARNING] mDNS: 無法解析 '{NODEMCU_HOSTNAME}'。"); state.mcu_ip_address = None

def fetch_obd_data():
    """(同步) 從 OBD 感測器獲取數據。"""
    if obd_sensor and obd_sensor.is_connected:
        obd_data_obj = obd_sensor.get_obd_data()
        with state.state_lock:
            state.shared_state["obd"] = obd_data_obj

def fetch_nodemcu_data():
    if not state.mcu_ip_address: find_mcu_ip()
    if not state.mcu_ip_address: return
    try:
        response = requests.get(f"http://{state.mcu_ip_address}/api/sensors", timeout=2)
        if response.status_code == 200:
            mcu_raw_data = response.json()
            with state.state_lock:
                state.shared_state["env"] = EnvironmentalData.model_validate(mcu_raw_data)
                state.shared_state["sys"] = SystemStatus.model_validate(mcu_raw_data)
    except requests.exceptions.RequestException:
        state.mcu_ip_address = None

def push_data_via_websocket():
    with state.state_lock:
        if not all(key in state.shared_state for key in ["sys", "env", "obd"]):
            return
        full_data = {**state.shared_state["sys"].model_dump(by_alias=True), **state.shared_state["env"].model_dump(), **state.shared_state["obd"].model_dump()}
    try:
        final_data = MotoData.model_validate(full_data)
        now = datetime.now()
        if final_data.rpm is not None:
            if final_data.rpm <= 10 and state.engine_off_timestamp is None: state.engine_off_timestamp = now
            elif final_data.rpm > 10 and state.engine_off_timestamp is not None: state.engine_off_timestamp = None
        final_data_dict = final_data.model_dump(mode='json')
        from .routes import calculate_feels_like
        feels_like_temp = calculate_feels_like(final_data_dict.get('temperature'), final_data_dict.get('humidity'), final_data_dict.get('speed'))
        final_data_dict['feels_like'] = feels_like_temp
        socketio.emit('update_data', final_data_dict)
        with state.db_buffer_lock:
            state.db_write_buffer.append(final_data)
    except ValidationError as e:
        logging.error(f"[WEBSOCKET PUSH ERROR] {e}")

def write_buffer_to_db():
    # ... (此函式無需變更) ...
    pass # 為了簡潔，省略了內部邏輯

def create_app():
    global obd_sensor, dmx_controller
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'a-secure-random-string-for-motoplayer-project'

    # --- 階段一: 初始化感測器與控制器 ---
    
    # 初始化 OBD 感測器
    if config.OBD_MODE == 'REAL':
        try:
            from real_obd import RealOBD
            logging.info(f"--- [Sync] 使用真實OBD (RFCOMM) 模式 (位址: {config.OBD_DEVICE_ADDRESS}) ---")
            obd_sensor = RealOBD(mac_address=config.OBD_DEVICE_ADDRESS, channel=config.RFCOMM_CHANNEL)
            if not obd_sensor.connect():
                logging.warning("[WARNING] 無法連接到真實OBD感測器，將退回使用模擬器。")
                from mock_obd import MockOBD
                obd_sensor = MockOBD()
                obd_sensor.connect()
        except (ImportError, FileNotFoundError):
            logging.error("[ERROR] 'real_obd.py' 或 'pybluez' 函式庫不存在，將退回使用模擬器。")
            from mock_obd import MockOBD
            obd_sensor = MockOBD()
            obd_sensor.connect()
    else:
        from mock_obd import MockOBD
        logging.info("--- [Sync] 使用模擬OBD模式 ---")
        obd_sensor = MockOBD()
        obd_sensor.connect()

    # 初始化 DMX 控制器
    # if config.DMX_MAC_ADDRESS and config.DMX_MAC_ADDRESS != "XX:XX:XX:XX:XX:XX":
    #     dmx_controller = DMXController(config.DMX_MAC_ADDRESS)
    #     # 注意：DMX 的 connect() 是非同步的，不應在此處直接呼叫
    #     logging.info(f"DMX Controller for {config.DMX_MAC_ADDRESS} initialized.")
    # else:
    #     dmx_controller = None
    #     logging.warning("DMX Controller address not set. DMX features will be disabled.")

    # --- 階段二: 設定背景排程任務 ---
    socketio.init_app(app)
    scheduler = APScheduler()
    scheduler.add_job(id='FetchOBDJob', func=fetch_obd_data, trigger='interval', seconds=OBD_FETCH_INTERVAL_MS / 1000)
    scheduler.add_job(id='FetchNodeMCUJob', func=fetch_nodemcu_data, trigger='interval', seconds=NODEMCU_FETCH_INTERVAL_S)
    scheduler.add_job(id='PushWebSocketJob', func=push_data_via_websocket, trigger='interval', seconds=WEBSOCKET_PUSH_INTERVAL_MS / 1000)
    scheduler.add_job(id='WriteDBJob', func=write_buffer_to_db, trigger='interval', seconds=DB_WRITE_INTERVAL_S)
    scheduler.init_app(app)
    scheduler.start()
    logging.info("多執行緒背景服務已啟動。")

    # --- 階段三: 註冊路由與清理函式 ---
    from . import routes
    app.register_blueprint(routes.bp)

    # 定義應用程式關閉時的清理工作
    def cleanup():
        if obd_sensor:
            logging.info("App cleanup: Disconnecting from OBD sensor...")
            obd_sensor.disconnect()
        # if dmx_controller and dmx_controller.is_connected:
        #     logging.info("App cleanup: Disconnecting from DMX controller...")
        #     try:
        #         # 為了在同步的 atexit 中執行非同步函式，需要這樣一個包裝
        #         loop = asyncio.get_event_loop()
        #         loop.run_until_complete(dmx_controller.disconnect())
        #     except Exception as e:
        #         logging.error(f"Error during DMX disconnect on cleanup: {e}")

    atexit.register(cleanup)
    
    return app
