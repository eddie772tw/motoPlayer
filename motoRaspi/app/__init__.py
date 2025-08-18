# app/__init__.py (v4.7 - DB Write Fix)
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

# --- OBD 感測器初始化 ---
obd_sensor = None
if config.OBD_MODE == 'REAL':
    try:
        from real_obd import RealOBD
        print(f"--- 使用真實OBD模式 (埠: {config.REAL_OBD_PORT}) ---")
        obd_sensor = RealOBD(port=config.REAL_OBD_PORT, baudrate=config.REAL_OBD_BAUDRATE)
        if not obd_sensor.connect():
            print("[WARNING] 無法連接到真實OBD感測器，將退回使用模擬器。")
            from mock_obd import MockOBD
            obd_sensor = MockOBD()
    except (ImportError, FileNotFoundError):
        print("[ERROR] 'real_obd.py' 檔案不存在或無法匯入，將退回使用模擬器。")
        from mock_obd import MockOBD
        obd_sensor = MockOBD()
else:
    from mock_obd import MockOBD
    print("--- 使用模擬OBD模式 ---")
    obd_sensor = MockOBD()


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

# --- 背景任務函式 ---
def find_mcu_ip():
    try:
        ip = socket.gethostbyname(NODEMCU_HOSTNAME)
        if ip != state.mcu_ip_address: print(f"[INFO] mDNS: '{NODEMCU_HOSTNAME}' -> {ip}"); state.mcu_ip_address = ip
    except socket.gaierror:
        if state.mcu_ip_address is not None: print(f"[WARNING] mDNS: 無法解析 '{NODEMCU_HOSTNAME}'。"); state.mcu_ip_address = None

def fetch_obd_data():
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
    """[低頻任務] 聚合緩衝區數據並批次寫入資料庫"""
    with state.db_buffer_lock:
        if not state.db_write_buffer: return
        local_buffer_copy = state.db_write_buffer.copy(); state.db_write_buffer.clear()
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 執行批次寫入，共收到 {len(local_buffer_copy)} 筆原始數據。")
    
    aggregated_records = []
    avg_fields = [
        'temperature', 'humidity', 'light_level', 'rpm', 'speed', 'coolant_temp', 
        'battery_voltage', 'throttle_pos', 'engine_load', 'abs_load_val', 
        'timing_advance', 'intake_air_temp', 'intake_map', 'short_term_fuel_trim_b1', 
        'long_term_fuel_trim_b1', 'o2_sensor_voltage_b1s1'
    ]
    int_fields = ['light_level', 'rpm', 'speed', 'intake_map']
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
        agg_record['rfid_card'] = group_list[-1].rfid_card
        agg_record['fuel_system_status'] = group_list[-1].fuel_system_status
        
        aggregated_records.append(MotoData.model_validate(agg_record))

    print(f"聚合後，將寫入 {len(aggregated_records)} 筆精簡數據。")
    
    try:
        now = datetime.now()
        if state.engine_off_timestamp and (now - state.engine_off_timestamp > timedelta(minutes=TRIP_TIMEOUT_MINUTES)):
            state.current_trip_id = None
        if state.current_trip_id is None:
            state.current_trip_id = int(now.timestamp())
            print(f"============== New Trip Started: {state.current_trip_id} ==============")

        # 修正: 準備要插入的數據元組 (tuple)，使其與 init_db.py 的結構完全匹配
        records_to_insert = [
            (
                dp.timestamp, state.current_trip_id, dp.uno_status, dp.rfid_card,
                dp.temperature, dp.humidity, dp.light_level,
                dp.rpm, dp.speed, dp.coolant_temp, dp.battery_voltage,
                dp.throttle_pos, dp.engine_load, dp.abs_load_val, dp.timing_advance,
                dp.intake_air_temp, dp.intake_map, dp.fuel_system_status,
                dp.short_term_fuel_trim_b1, dp.long_term_fuel_trim_b1,
                dp.o2_sensor_voltage_b1s1
            ) for dp in aggregated_records
        ]
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # 修正: INSERT SQL 陳述式，使其與 init_db.py 的結構完全匹配
        insert_sql = """
            INSERT INTO telemetry_data (
                timestamp, trip_id, uno_status, rfid_card, temperature, humidity, light_level,
                rpm, speed, coolant_temp, battery_voltage,
                throttle_pos, engine_load, abs_load_val, timing_advance,
                intake_air_temp, intake_map, fuel_system_status,
                short_term_fuel_trim_b1, long_term_fuel_trim_b1, o2_sensor_voltage_b1s1
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
