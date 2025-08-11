# app/__init__.py (v4.6 - Attribute Fix)
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
from mock_obd import MockOBD

# --- 設定 (維持不變) ---
NODEMCU_HOSTNAME = "motoplayer.local"
DATABASE_PATH = "motoplayer.db"
TRIP_TIMEOUT_MINUTES = 30
OBD_FETCH_INTERVAL_MS = 200
NODEMCU_FETCH_INTERVAL_S = 2.5
WEBSOCKET_PUSH_INTERVAL_MS = 200
DB_WRITE_INTERVAL_S = 60

# --- 初始化 (維持不變) ---
mock_obd_sensor = MockOBD()
socketio = SocketIO()

# --- 背景任務函式 (維持不變) ---
def find_mcu_ip():
    try:
        ip = socket.gethostbyname(NODEMCU_HOSTNAME)
        if ip != state.mcu_ip_address: print(f"[INFO] mDNS: '{NODEMCU_HOSTNAME}' -> {ip}"); state.mcu_ip_address = ip
    except socket.gaierror:
        if state.mcu_ip_address is not None: print(f"[WARNING] mDNS: 無法解析 '{NODEMCU_HOSTNAME}'。"); state.mcu_ip_address = None

def fetch_obd_data():
    obd_data_obj = mock_obd_sensor.get_obd_data()
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
    """[低頻任務] 聚合緩衝區數據並批次寫入資料庫"""
    with state.db_buffer_lock:
        if not state.db_write_buffer: return
        local_buffer_copy = state.db_write_buffer.copy(); state.db_write_buffer.clear()
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 執行批次寫入，共收到 {len(local_buffer_copy)} 筆原始數據。")
    
    aggregated_records = []
    avg_fields = ['temperature', 'humidity', 'light_level', 'rpm', 'speed', 'coolant_temp', 'battery_voltage']
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
                if field in int_fields:
                    agg_record[field] = int(round(avg_value))
                else:
                    agg_record[field] = avg_value

        agg_record['gear'] = group_list[-1].gear
        agg_record['uno_status'] = group_list[-1].uno_status
        
        aggregated_records.append(MotoData.model_validate(agg_record))

    print(f"聚合後，將寫入 {len(aggregated_records)} 筆精簡數據。")
    
    try:
        now = datetime.now()
        if state.engine_off_timestamp and (now - state.engine_off_timestamp > timedelta(minutes=TRIP_TIMEOUT_MINUTES)):
            state.current_trip_id = None
        if state.current_trip_id is None:
            state.current_trip_id = int(now.timestamp())
            print(f"============== New Trip Started: {state.current_trip_id} ==============")

        # [修改] 修正此處的拼寫錯誤 (rf_id_card -> rfid_card)
        records_to_insert = [(dp.timestamp, state.current_trip_id, dp.uno_status, dp.rfid_card, dp.temperature, dp.humidity, dp.light_level, dp.rpm, dp.speed, dp.coolant_temp, dp.battery_voltage, dp.gear) for dp in aggregated_records]
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        insert_sql = "INSERT INTO telemetry_data (timestamp, trip_id, uno_status, rfid_card, temperature, humidity, light_level, rpm, speed, coolant_temp, battery_voltage, gear) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"
        cursor.executemany(insert_sql, records_to_insert)
        conn.commit(); conn.close()
    except Exception as e:
        print(f"[WRITE DB ERROR] {e}")


def create_app():
    # (此函式維持不變)
    app = Flask(__name__)
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
