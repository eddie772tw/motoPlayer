# app/__init__.py (v5.2 - Async Bridge Fix)
#
# 版本更新說明:
# 此版本已進行重構，以完全支援新的非同步 real_obd.py (BLE) 和 mock_obd.py。
# 主要變更:
# 1. OBD 初始化邏輯移至一個非同步函式 `initialize_obd_sensor` 中。
# 2. 背景任務 `fetch_obd_data` 已轉換為 `async def`，並使用 `await` 來呼叫 OBD 資料獲取函式。
# 3. 在應用程式啟動時，會先執行一次非同步的感測器初始化。
# 4. [FIX] 修正了 APScheduler 新增非同步任務的方法，從錯誤的 `scheduler.api.add_job` 改回正確的 `scheduler.add_job`。
# 5. [FIX] 將 fetch_obd_data 改回同步函式，並在內部使用 asyncio.run() 來執行非同步的 get_obd_data，解決同步/非同步混用問題。

import asyncio
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

# --- 全域 OBD 感測器實例 ---
# 注意: 初始化時為 None，將在應用啟動時透過非同步函式進行實例化和連線。
obd_sensor = None

# --- 設定 (與原版相同) ---
NODEMCU_HOSTNAME = "motoplayer.local"
DATABASE_PATH = "motoplayer.db"
TRIP_TIMEOUT_MINUTES = 30
OBD_FETCH_INTERVAL_MS = 200
NODEMCU_FETCH_INTERVAL_S = 2.5
WEBSOCKET_PUSH_INTERVAL_MS = 200
DB_WRITE_INTERVAL_S = 60

# --- 初始化 ---
socketio = SocketIO()

# =================================================================
# --- 非同步 OBD 感測器初始化 ---
# =================================================================
async def initialize_obd_sensor():
    """
    (非同步) 在應用程式啟動時執行，負責建立 OBD 感測器實例並嘗試連線。
    """
    global obd_sensor
    
    if config.OBD_MODE == 'REAL':
        try:
            from real_obd import RealOBD
            print(f"--- [Async] 使用真實OBD (BLE) 模式 (位址: {config.OBD_BLE_ADDRESS}) ---")
            # 傳入設定檔中的 BLE 位址
            obd_sensor = RealOBD(device_address=config.OBD_BLE_ADDRESS)
            if not await obd_sensor.connect():
                print("[WARNING] 無法連接到真實OBD (BLE) 感測器，將退回使用模擬器。")
                from mock_obd import MockOBD
                obd_sensor = MockOBD()
                await obd_sensor.connect() # 連接模擬器
        except (ImportError, FileNotFoundError):
            print("[ERROR] 'real_obd.py' 檔案不存在或無法匯入，將退回使用模擬器。")
            from mock_obd import MockOBD
            obd_sensor = MockOBD()
            await obd_sensor.connect() # 連接模擬器
    else:
        from mock_obd import MockOBD
        print("--- [Async] 使用模擬OBD模式 ---")
        obd_sensor = MockOBD()
        await obd_sensor.connect() # 連接模擬器

# =================================================================
# --- 背景任務函式 (部分已修改為 Async) ---
# =================================================================

def find_mcu_ip():
    # 此函式不涉及 I/O 密集操作，保持同步即可
    try:
        ip = socket.gethostbyname(NODEMCU_HOSTNAME)
        if ip != state.mcu_ip_address: print(f"[INFO] mDNS: '{NODEMCU_HOSTNAME}' -> {ip}"); state.mcu_ip_address = ip
    except socket.gaierror:
        if state.mcu_ip_address is not None: print(f"[WARNING] mDNS: 無法解析 '{NODEMCU_HOSTNAME}'。"); state.mcu_ip_address = None

# [FIXED] 改回同步函式，作為同步與非同步之間的橋樑
def fetch_obd_data():
    """(同步) 從 OBD 感測器獲取數據的排程任務。"""
    if obd_sensor:
        try:
            # [FIXED] 在同步函式中，使用 asyncio.run() 來執行並等待非同步函式完成
            obd_data_obj = asyncio.run(obd_sensor.get_obd_data())
            with state.state_lock:
                state.shared_state["obd"] = obd_data_obj
        except Exception as e:
            print(f"[ERROR in fetch_obd_data]: {e}")


def fetch_nodemcu_data():
    # 此函式使用 requests，為同步 I/O，保持不變
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
    # 此函式主要處理內部狀態和 socketio.emit，保持同步
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
    # 此函式為 CPU 密集和同步的資料庫 I/O，保持不變
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

    # 在啟動排程器之前，先執行非同步的感測器初始化
    print("正在執行非同步 OBD 感測器初始化...")
    asyncio.run(initialize_obd_sensor())
    print("OBD 感測器初始化完成。")

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
