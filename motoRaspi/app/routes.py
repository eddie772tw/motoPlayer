# app/routes.py

import sqlite3
import math
import requests
import io
import csv
import os
import pandas as pd
from werkzeug.utils import secure_filename
from flask import Blueprint, jsonify, request, render_template, Response, flash, redirect, url_for
from . import state
from datetime import datetime, timedelta

DATABASE_PATH = "motoplayer.db"
bp = Blueprint('main', __name__)

def get_db_connection():
    """建立並回傳一個資料庫連線物件。"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row 
    return conn

def calculate_feels_like(temp_c, humidity, speed_kmh):
    """根據溫度、濕度和速度計算體感溫度。"""
    if temp_c is None or humidity is None or speed_kmh is None: return None
    vapor_pressure = (humidity / 100) * 6.105 * math.exp(17.27 * temp_c / (237.7 + temp_c))
    wind_speed_ms = speed_kmh / 3.6
    apparent_temp = temp_c + (0.33 * vapor_pressure) - (0.70 * wind_speed_ms) - 4.00
    return round(apparent_temp, 1)

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    """檢查檔案副檔名是否合法"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 全新的欄位對應字典，專為「寬格式」CSV 設計 ---
COLUMN_MAPPING = {
    '发动机转速 (rpm)': 'rpm',
    '速度 (GPS) (km/h)': 'speed',
    '冷却液温度 (℃)': 'coolant_temp',
    '控制模块电压 (V)': 'battery_voltage',
    '节气门位置 (%)': 'throttle_pos',
    '计算出的发动机负荷值 (%)': 'engine_load',
    '正时提前 (°)': 'timing_advance',
    '进气温度 (℃)': 'intake_air_temp',
    '进气歧管绝对压力 (kPa)': 'intake_map',
    '氧传感器1 单元1 电压 (V)': 'o2_sensor_voltage_b1s1',
    '氧传感器1 单元1 短期燃油修正 (%)': 'short_term_fuel_trim_b1',
    '长期燃油修正% - 单元1 (%)': 'long_term_fuel_trim_b1',
    'fuel_system_status': 'fuel_system_status' # 假設欄位名稱直接對應
}


@bp.route("/")
def index():
    return render_template('index.html')

@bp.route("/history")
def history():
    return render_template('history.html')

@bp.route("/trip/<int:trip_id>")
def trip_detail(trip_id):
    return render_template('trip_detail.html', trip_id=trip_id)


@bp.route("/api/realtime_data")
def get_realtime_data():
    latest_data = None;
    with state.state_lock:
        if "obd" in state.shared_state and state.shared_state["obd"] is not None:
             latest_data = {**state.shared_state["sys"].model_dump(by_alias=True), **state.shared_state["env"].model_dump(), **state.shared_state["obd"].model_dump()}
    
    if latest_data is None:
        try:
            conn = get_db_connection(); latest_data_row = conn.execute("SELECT * FROM telemetry_data ORDER BY id DESC LIMIT 1").fetchone(); conn.close()
            if latest_data_row: latest_data = dict(latest_data_row)
        except Exception as e:
            print(f"[API ERROR] /api/realtime_data DB fallback failed: {e}"); return jsonify({"error": "An internal server error occurred."}), 500
    
    if latest_data is None: return jsonify({"error": "No data available."}), 404
    
    try:
        feels_like_temp = calculate_feels_like(latest_data.get('temperature'), latest_data.get('humidity'), latest_data.get('speed'))
        latest_data['feels_like'] = feels_like_temp; return jsonify(latest_data)
    except Exception as e:
        print(f"[API ERROR] /api/realtime_data processing failed: {e}"); return jsonify({"error": "An internal server error occurred."}), 500


@bp.route("/api/trip_history")
def get_trip_history():
    try:
        conn = get_db_connection()
        history_rows = conn.execute("SELECT trip_id, MIN(timestamp) as start_time, MAX(timestamp) as end_time, COUNT(id) as data_points, MAX(speed) as max_speed FROM telemetry_data WHERE trip_id IS NOT NULL GROUP BY trip_id ORDER BY trip_id DESC;").fetchall()
        conn.close(); history_list = [dict(row) for row in history_rows]; return jsonify(history_list)
    except Exception as e:
        print(f"[API ERROR] /api/trip_history: {e}"); return jsonify({"error": "An internal server error occurred."}), 500

@bp.route("/api/trip_data")
def get_trip_data():
    trip_id = request.args.get('id', type=int)
    if trip_id is None: return jsonify({"error": "Missing 'id' parameter."}), 400
    try:
        conn = get_db_connection()
        trip_data_rows = conn.execute("SELECT * FROM telemetry_data WHERE trip_id = ? ORDER BY id ASC;", (trip_id,)).fetchall()
        conn.close(); trip_data_list = [dict(row) for row in trip_data_rows]
        if not trip_data_list: return jsonify({"error": f"No data found for trip_id {trip_id}."}), 404
        return jsonify(trip_data_list)
    except Exception as e:
        print(f"[API ERROR] /api/trip_data: {e}"); return jsonify({"error": "An internal server error occurred."}), 500


@bp.route("/api/upload_log", methods=['POST'])
def upload_log():
    """
    全新重構的 CSV 上傳函式，專為處理「寬格式」日誌檔設計。
    """
    if 'log_file' not in request.files:
        flash('請求中沒有檔案部分', 'error')
        return redirect(url_for('main.history'))
    
    file = request.files['log_file']
    if file.filename == '':
        flash('未選擇檔案', 'error')
        return redirect(url_for('main.history'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        conn = None
        try:
            df = pd.read_csv(file, sep=',')
            df.rename(columns=COLUMN_MAPPING, inplace=True)

            try:
                date_str = filename.split('_')[0]
                log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except (ValueError, IndexError):
                log_date = datetime.now().date()

            df['timestamp'] = df['time'].apply(lambda t: datetime.combine(log_date, datetime.strptime(t, '%H:%M:%S.%f').time()))

            conn = get_db_connection()
            cursor = conn.cursor()
            max_trip_id_row = cursor.execute("SELECT MAX(trip_id) FROM telemetry_data").fetchone()
            new_trip_id = (max_trip_id_row[0] or 0) + 1

            db_columns_info = cursor.execute("PRAGMA table_info(telemetry_data);").fetchall()
            db_columns = [col['name'] for col in db_columns_info]
            
            # 修正 1: 加上 .copy() 來避免 SettingWithCopyWarning
            df_to_insert = df[[col for col in df.columns if col in db_columns]].copy()
            df_to_insert['trip_id'] = new_trip_id

            for db_col in db_columns:
                if db_col not in df_to_insert.columns:
                    df_to_insert[db_col] = None
            
            # 修正 2: 將 pandas Timestamp 物件轉換為 SQLite 相容的字串格式
            df_to_insert['timestamp'] = df_to_insert['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]

            # 按照資料庫欄位順序排列，並轉換為元組列表
            records_to_insert = [tuple(row) for row in df_to_insert[db_columns].to_numpy()]
            
            placeholders = ', '.join(['?'] * len(db_columns))
            sql = f"INSERT INTO telemetry_data ({', '.join(db_columns)}) VALUES ({placeholders});"

            cursor.executemany(sql, records_to_insert)
            conn.commit()
            
            flash(f'檔案 "{filename}" 已成功匯入，新的騎行 ID 為 {new_trip_id}。', 'success')

        except Exception as e:
            if conn:
                conn.rollback()
            print(f"[UPLOAD API ERROR] 處理檔案時發生錯誤: {e}")
            flash(f'處理檔案 "{filename}" 時發生錯誤: {e}', 'error')
        finally:
            if conn:
                conn.close()
        
        return redirect(url_for('main.history'))

    else:
        flash('不支援的檔案類型，請上傳 .csv 檔案。', 'error')
        return redirect(url_for('main.history'))


@bp.route("/api/command", methods=['POST'])
def handle_command():
    if not state.mcu_ip_address: return jsonify({"status": "error", "message": "NodeMCU is currently offline."}), 503
    data = request.get_json();
    if not data or 'command' not in data: return jsonify({"status": "error", "message": "Invalid JSON request body."}), 400
    command = data.get('command'); param = data.get('param')
    command_map = {"vol_up": "/api/vol_up", "vol_down": "/api/vol_down", "restart": "/api/restart"}
    target_url = None; base_url = f"http://{state.mcu_ip_address}"
    if command in command_map: target_url = base_url + command_map[command]
    elif command == "play" and param is not None: target_url = f"{base_url}/api/play?track={param}"
    else: return jsonify({"status": "error", "message": f"Unknown or invalid command: '{command}'"}), 400
    try:
        print(f"[COMMAND API] Forwarding command '{command}' to {target_url}")
        response = requests.get(target_url, timeout=3); response.raise_for_status()
        return jsonify({"status": "success", "command_sent": command, "nodemcu_response": response.text}), 200
    except requests.exceptions.RequestException as e:
        print(f"[COMMAND API ERROR] Failed to send command to NodeMCU: {e}"); return jsonify({"status": "error", "message": "Failed to communicate with NodeMCU."}), 504

@bp.route("/api/trip/<int:trip_id>", methods=['DELETE'])
def delete_trip(trip_id):
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("DELETE FROM telemetry_data WHERE trip_id = ?;", (trip_id,)); conn.commit()
        deleted_rows = cursor.rowcount; conn.close()
        if deleted_rows > 0:
            print(f"[DELETE API] Successfully deleted {deleted_rows} records for trip_id {trip_id}.")
            return jsonify({"status": "success", "message": f"Trip {trip_id} deleted.", "deleted_records": deleted_rows}), 200
        else:
            return jsonify({"status": "error", "message": f"No records found for trip_id {trip_id}."}), 404
    except Exception as e:
        print(f"[DELETE API ERROR] /api/trip/{trip_id}: {e}"); return jsonify({"status": "error", "message": "An internal server error occurred."}), 500

@bp.route("/api/trip/<int:trip_id>/export")
def export_trip_csv(trip_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM telemetry_data WHERE trip_id = ? ORDER BY id ASC;", (trip_id,))
        rows = cursor.fetchall()
        
        if not rows:
            return "No data found for this trip ID", 404

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([description[0] for description in cursor.description])
        for row in rows:
            writer.writerow(row)
        
        conn.close()

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=trip_{trip_id}_data.csv"}
        )
    except Exception as e:
        print(f"[EXPORT API ERROR] /api/trip/{trip_id}/export: {e}")
        return "An internal server error occurred.", 500
