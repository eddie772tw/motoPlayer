# app/__init__.py (v6.0 - Synchronous Final)
#
# 版本更新說明:
# 此版本已完全還原為同步架構，以配合使用 PyBluez 的傳統藍牙 RFCOMM 方案。
# - 移除了所有 asyncio 相關的程式碼。
# - OBD 感測器在應用程式啟動時直接進行同步初始化。
# - 所有 APScheduler 任務均為標準的同步任務。

import sqlite3
import time
import socket
import requests
from flask import Flask
from flask_socketio import SocketIO
from flask_apscheduler import APScheduler
from pydantic import ValidationError
from datetime import datetime, timedelta
from threading import Lock
from itertools import groupby
from statistics import mean

from . import state
from app.models import MotoData, EnvironmentalData, SystemStatus
import config

# --- OBD 感測器初始化 (同步) ---
obd_sensor = None
if config.OBD_MODE == 'REAL':
    try:
        from real_obd import RealOBD
        print(f"--- [Sync] 使用真實OBD (RFCOMM) 模式 (位址: {config.OBD_DEVICE_ADDRESS}) ---")
        obd_sensor = RealOBD(mac_address=config.OBD_DEVICE_ADDRESS, channel=config.RFCOMM_CHANNEL)
        if not obd_sensor.connect():
            print("[WARNING] 無法連接到真實OBD感測器，將退回使用模擬器。")
            from mock_obd import MockOBD
            obd_sensor = MockOBD()
            obd_sensor.connect()
    except (ImportError, FileNotFoundError):
        print("[ERROR] 'real_obd.py' 或 'pybluez' 函式庫不存在，將退回使用模擬器。")
        from mock_obd import MockOBD
        obd_sensor = MockOBD()
        obd_sensor.connect()
else:
    from mock_obd import MockOBD
    print("--- [Sync] 使用模擬OBD模式 ---")
    obd_sensor = MockOBD()
    obd_sensor.connect()


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
        if ip != state.mcu_ip_address: print(f"[INFO] mDNS: '{NODEMCU_HOSTNAME}' -> {ip}"); state.mcu_ip_address = ip
    except socket.gaierror:
        if state.mcu_ip_address is not None: print(f"[WARNING] mDNS: 無法解析 '{NODEMCU_HOSTNAME}'。"); state.mcu_ip_address = None

def fetch_obd_data():
    """(同步) 從 OBD 感測器獲取數據。"""
    if obd_sensor:
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
        print(f"[WEBSOCKET PUSH ERROR] {e}")

def write_buffer_to_db():
    # ... (此函式無需變更) ...
    with state.db_buffer_lock:
        if not state.db_write_buffer: return
        local_buffer_copy = state.db_write_buffer.copy(); state.db_write_buffer.clear()
    
    # ... (後續聚合與寫入邏輯保持不變) ...
    aggregated_records = []
    avg_fields = [
        'temperature', 'humidity', 'light_level', 'rpm', 'speed', 'coolant_temp', 
        'battery_voltage'
    ]
    int_fields = ['light_level', 'rpm', 'speed']
    keyfunc = lambda x: x.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    
    for _, group in groupby(sorted(local_buffer_copy, key=keyfunc), key=keyfunc):
        group_list = list(group)
        if not group_list: continue
        
        agg_record = group_list[0].model_dump()
        
        for field in avg_fields:
            values = [getattr(item, field) for item in group_list if getattr(item, field) is not None]
            if values:
                avg_value = mean(values)
                agg_record[field] = int(round(avg_value)) if field in int_fields else avg_value

        agg_record['uno_status'] = group_list[-1].uno_status
        
        aggregated_records.append(MotoData.model_validate(agg_record))
    
    try:
        now = datetime.now()
        if state.engine_off_timestamp and (now - state.engine_off_timestamp > timedelta(minutes=TRIP_TIMEOUT_MINUTES)):
            state.current_trip_id = None
        if state.current_trip_id is None:
            state.current_trip_id = int(now.timestamp())
            print(f"============== New Trip Started: {state.current_trip_id} ==============")

        records_to_insert = [
            (
                dp.timestamp, state.current_trip_id, dp.uno_status,
                dp.temperature, dp.humidity, dp.light_level,
                dp.rpm, dp.speed, dp.coolant_temp, dp.battery_voltage
            ) for dp in aggregated_records
        ]
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        insert_sql = """
            INSERT INTO telemetry_data (
                timestamp, trip_id, uno_status, temperature, humidity, light_level,
                rpm, speed, coolant_temp, battery_voltage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        cursor.executemany(insert_sql, records_to_insert)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WRITE DB ERROR] {e}")


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'a-secure-random-string-for-motoplayer-project'

    socketio.init_app(app)
    scheduler = APScheduler()
    scheduler.add_job(id='FetchOBDJob', func=fetch_obd_data, trigger='interval', seconds=OBD_FETCH_INTERVAL_MS / 1000)
    scheduler.add_job(id='FetchNodeMCUJob', func=fetch_nodemcu_data, trigger='interval', seconds=NODEMCU_FETCH_INTERVAL_S)
    scheduler.add_job(id='PushWebSocketJob', func=push_data_via_websocket, trigger='interval', seconds=WEBSOCKET_PUSH_INTERVAL_MS / 1000)
    scheduler.add_job(id='WriteDBJob', func=write_buffer_to_db, trigger='interval', seconds=DB_WRITE_INTERVAL_S)
    scheduler.init_app(app)
    scheduler.start()
    
    print("多執行緒背景服務已啟動。")
    from . import routes
    app.register_blueprint(routes.bp)
    return app
