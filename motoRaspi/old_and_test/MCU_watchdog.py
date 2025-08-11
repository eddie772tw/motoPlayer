import requests
import time
import socket
from pydantic import ValidationError

# =================================================================
# --- 專案模組匯入 (Project Module Imports) ---
# =================================================================
# 專案結構假設:
# /project_root
# ├── MCU_watchdog.py  (此檔案)
# ├── mock_obd.py
# └── /app
#     ├── __init__.py
#     └── models.py
try:
    from app.models import MotoData
    from mock_obd import MockOBD
except ImportError:
    print("[FATAL ERROR] 無法匯入 'app' 或 'mock_obd' 模組。請確認您的檔案結構是否正確。")
    exit()

# =================================================================
# --- 設定 (Configuration) ---
# =================================================================
NODEMCU_HOSTNAME = "motoplayer.local"
POLLING_INTERVAL_SECONDS = 2.5

# =================================================================
# --- 初始化 (Initialization) ---
# =================================================================
mcu_ip_address = None
# 初始化模擬 OBD 感測器
mock_obd_sensor = MockOBD()
print("[INFO] Mock OBD-II sensor initialized.")

# =================================================================
# --- 函式定義 (Function Definitions) ---
# =================================================================

def find_mcu_ip() -> bool:
    """使用 mDNS 解析 NodeMCU 的 IP 位址，成功則回傳 True。"""
    global mcu_ip_address
    print(f"[INFO] mDNS: 正在嘗試解析 '{NODEMCU_HOSTNAME}'...")
    try:
        mcu_ip_address = socket.gethostbyname(NODEMCU_HOSTNAME)
        print(f"[INFO] mDNS: 成功！ '{NODEMCU_HOSTNAME}' 解析為 {mcu_ip_address}")
        return True
    except socket.gaierror:
        print(f"[WARNING] mDNS: 無法解析 '{NODEMCU_HOSTNAME}'。")
        mcu_ip_address = None
        return False

def get_data_from_nodemcu() -> dict:
    """
    從 NodeMCU 獲取原始感測器數據。
    成功時回傳一個字典，失敗則回傳空字典。
    """
    if not mcu_ip_address:
        # print("[ERROR] 無法獲取數據：未知的 NodeMCU IP 位址。") # 在主迴圈中已有提示，此處可精簡
        return {}

    api_url = f"http://{mcu_ip_address}/api/sensors"
    try:
        response = requests.get(api_url, timeout=3)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[ERROR] NodeMCU 回應狀態碼: {response.status_code}")
            return {}
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] 對 {mcu_ip_address} 的網路請求失敗: {e}")
        return {}

# =================================================================
# --- 主程式進入點 (Main Execution) ---
# =================================================================

if __name__ == "__main__":
    print("--- MCU Watchdog Service v3.1 (Single-Line Log) ---")
    print("正在監控 NodeMCU 並整合模擬的 OBD-II 數據...")

    while True:
        # 1. 確保 NodeMCU 的 IP 位址是已知的
        if not mcu_ip_address:
            find_mcu_ip()
            if not mcu_ip_address:
                time.sleep(POLLING_INTERVAL_SECONDS)
                continue

        # 2. 從各個來源獲取數據
        mcu_raw_data = get_data_from_nodemcu()
        obd_data_obj = mock_obd_sensor.get_obd_data()

        # 3. 數據整合與驗證
        if mcu_raw_data:
            try:
                combined_data = {**mcu_raw_data, **obd_data_obj.model_dump()}
                final_data = MotoData(**combined_data)

                # 4. 格式化並顯示為單行日誌
                #    移除了 model_dump_json 中的 indent 參數，使其輸出為單行
                log_line = (
                    f"[{final_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"{final_data.model_dump_json(exclude={'timestamp'})}"
                )
                print(log_line)

            except ValidationError as e:
                print(f"[VALIDATION ERROR] 數據模型驗證失敗:\n{e}")
            except Exception as e:
                print(f"[UNEXPECTED ERROR] 處理數據時發生錯誤: {e}")
        else:
            print(f"[WARNING] 無法從 NodeMCU 獲取數據。將在下個週期重新搜尋。")
            mcu_ip_address = None

        # 5. 等待指定的間隔時間
        time.sleep(POLLING_INTERVAL_SECONDS)
