# app/state.py
"""
這個模組用於存放所有跨檔案共享的全域狀態變數，
以解決循環匯入 (Circular Import) 的問題。
"""
from threading import Lock
from .models import OBDData, EnvironmentalData, SystemStatus

# --- 全域變數與初始化 ---
mcu_ip_address = None

# --- 共享數據狀態與緩衝區 ---
# 用於 WebSocket 推送的即時數據
shared_state = {
    "obd": OBDData(),
    "env": EnvironmentalData(),
    "sys": SystemStatus()
}
state_lock = Lock()

# 用於批次寫入資料庫的數據緩衝區
db_write_buffer = []
db_buffer_lock = Lock()

# 用於追蹤騎行日誌 (Trip) 的變數
current_trip_id = None
engine_off_timestamp = None