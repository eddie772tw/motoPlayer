# app/routes.py

import sqlite3
import math
import requests
import io
import csv
from flask import Blueprint, jsonify, request, render_template, Response
from . import state

DATABASE_PATH = "motoplayer.db"
bp = Blueprint('main', __name__)

def get_db_connection():
    """建立並回傳一個資料庫連線物件。"""
    conn = sqlite3.connect(DATABASE_PATH)
    # 讓查詢結果可以像字典一樣透過欄位名稱存取
    conn.row_factory = sqlite3.Row 
    return conn

def calculate_feels_like(temp_c, humidity, speed_kmh):
    """根據溫度、濕度和速度計算體感溫度。"""
    if temp_c is None or humidity is None or speed_kmh is None: return None
    vapor_pressure = (humidity / 100) * 6.105 * math.exp(17.27 * temp_c / (237.7 + temp_c))
    wind_speed_ms = speed_kmh / 3.6
    apparent_temp = temp_c + (0.33 * vapor_pressure) - (0.70 * wind_speed_ms) - 4.00
    return round(apparent_temp, 1)

# --- 主要頁面路由 (Web Page Routes) ---

@bp.route("/")
def index():
    """渲染即時儀表板頁面。"""
    return render_template('index.html')

@bp.route("/history")
def history():
    """渲染騎行日誌列表頁面。"""
    return render_template('history.html')

@bp.route("/trip/<int:trip_id>")
def trip_detail(trip_id):
    """渲染單次騎行詳情分析頁面。"""
    return render_template('trip_detail.html', trip_id=trip_id)

# --- API 端點 (API Endpoints) ---

@bp.route("/api/realtime_data")
def get_realtime_data():
    """
    獲取最新一筆的遙測數據，主要用於 WebSocket 推送前的初始數據填充。
    """
    latest_data = None;
    with state.state_lock:
        if state.shared_state["obd"] or state.shared_state["env"]:
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
    """
    查詢並回傳所有歷史騎行的摘要列表，供 history.html 使用。
    """
    try:
        conn = get_db_connection()
        history_rows = conn.execute("SELECT trip_id, MIN(timestamp) as start_time, MAX(timestamp) as end_time, COUNT(id) as data_points, MAX(speed) as max_speed FROM telemetry_data WHERE trip_id IS NOT NULL GROUP BY trip_id ORDER BY trip_id DESC;").fetchall()
        conn.close(); history_list = [dict(row) for row in history_rows]; return jsonify(history_list)
    except Exception as e:
        print(f"[API ERROR] /api/trip_history: {e}"); return jsonify({"error": "An internal server error occurred."}), 500

@bp.route("/api/trip_data")
def get_trip_data():
    """
    根據 trip_id，查詢並回傳該次騎行的所有詳細數據點。
    這是 trip_detail.html 頁面中所有圖表的數據來源。
    由於使用 'SELECT *'，它會自動包含所有我們在資料庫中新增的欄位。
    """
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

@bp.route("/api/command", methods=['POST'])
def handle_command():
    """接收並處理來自 App (透過藍牙橋接器) 的控制指令。"""
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
    """刪除指定 trip_id 的所有相關數據。"""
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
    """
    根據 trip_id 將該次騎行的所有原始數據匯出為 CSV 檔案。
    """
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
