# real_obd.py (RFCOMM Final)
#
# 版本: 6.5 (Clean Logging)
# 描述: 此版本已重構，移除了所有內部的解析邏輯，
#      改為呼叫外部的 obd_converter 模組來處理數據轉換。
#      將所有 print() 語句替換為標準的 logging 模組。
#      [NEW] 移除了日誌訊息中的 [*], [+] 等標籤，使輸出更簡潔。

import bluetooth
import time
import logging
from typing import Optional

# [MODIFIED] 導入新的轉換模組
from obd_converter import decode_pid_response

try:
    from app.models import OBDData
except ImportError:
    # 在獨立執行時，這個警告是正常的
    logging.warning("無法匯入 'app.models'。將使用內部模擬的 OBDData 類別。")
    class OBDData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def __repr__(self): return f"OBDData({self.__dict__})"

# =================================================================
# ---               ELM327 指令集 (Constants)                   ---
# =================================================================

ELM327_INIT_SEQUENCE = [
    "ATZ",
    "ATE0",
    "ATL0",
    "ATH0",
    "ATSP5",
]

# [MODIFIED] 擴充我們想要輪詢的 PID 列表
PIDS_TO_QUERY = {
    "rpm": "010C",
    "speed": "010D",
    "coolant_temp": "0105",
    "engine_load": "0104",
    "throttle_pos": "0111",
    "battery_voltage": "ATRV", # 特殊 AT 指令
}

class RealOBD:
    """
    透過 RFCOMM Socket 與真實的 ELM327 OBD-II 適配器進行同步通訊的類別。
    """
    def __init__(self, mac_address, channel=1):
        self.mac_address = mac_address
        self.channel = channel
        self.sock: Optional[bluetooth.BluetoothSocket] = None
        self.is_connected = False

    def connect(self) -> bool:
        logging.info(f"正在嘗試連線到 {self.mac_address} 的 RFCOMM 頻道 {self.channel}...")
        try:
            self.sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.sock.connect((self.mac_address, self.channel))
            self.sock.settimeout(5.0)
            logging.info("RFCOMM Socket 連線成功！")

            logging.info("正在執行 ELM327 初始化序列...")
            for cmd in ELM327_INIT_SEQUENCE:
                response = self._send_command(cmd)
                logging.info(f"  > {cmd:<5}... {response.splitlines()[0]}")
                if "OK" not in response and "ELM" not in response:
                    logging.error(f"初始化指令 '{cmd}' 失敗，中止連線。")
                    self.disconnect()
                    return False
                time.sleep(0.1)
            
            logging.info("正在嘗試與 ECU 進行首次通訊 (0100)...")
            response = self._send_command("0100")
            if "NO DATA" in response or "ERROR" in response:
                 logging.error(f"無法與 ECU 建立通訊: {response.splitlines()[0]}")
                 self.disconnect()
                 return False

            logging.info("ECU 通訊已建立！OBD 感測器準備就緒。")
            self.is_connected = True
            return True

        except Exception as e:
            logging.error(f"連線或初始化失敗: {e}")
            self.disconnect()
            return False

    def disconnect(self):
        if self.sock:
            self.sock.close()
        self.sock = None
        self.is_connected = False
        logging.info("OBD-II (RFCOMM) 連線已關閉。")

    def _send_command(self, command: str) -> str:
        if not self.sock:
            return "ERROR: NOT CONNECTED"
        
        try:
            while self.sock.recv(1024): pass
        except bluetooth.btcommon.BluetoothError:
            pass

        self.sock.send((command + '\r').encode('utf-8'))
        
        buffer = ""
        while True:
            try:
                data = self.sock.recv(1024)
                if not data:
                    break
                buffer += data.decode('utf-8', errors='ignore')
                if '>' in buffer:
                    break
            except bluetooth.btcommon.BluetoothError as e:
                if "timed out" in str(e):
                    return "ERROR: TIMEOUT"
                raise e
        return buffer.strip()

    def _parse_voltage(self, response: str) -> Optional[float]:
        """處理 ATRV 指令的特殊解析函式"""
        try:
            return float(response.replace("V", ""))
        except:
            return None

    def get_obd_data(self) -> OBDData:
        """獲取核心儀表板數據，並打包成 OBDData 物件。"""
        if not self.is_connected:
            return OBDData()

        results = {}
        for key, pid in PIDS_TO_QUERY.items():
            raw_response = self._send_command(pid)
            
            if pid == "ATRV":
                results[key] = self._parse_voltage(raw_response)
            else:
                results[key] = decode_pid_response(pid, raw_response)
        
        return OBDData(**results)

if __name__ == '__main__':
    # --- 獨立執行時的日誌設定 ---
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
    
    TEST_DEVICE_ADDRESS = "66:1E:32:8A:55:2C"
    
    logging.info("--- RealOBD (RFCOMM) 獨立測試模式 ---")
    
    obd_sensor = RealOBD(mac_address=TEST_DEVICE_ADDRESS)
    
    try:
        if obd_sensor.connect():
            logging.info("--- 開始循環讀取數據 (每秒一次)，按 Ctrl+C 結束 ---")
            while True:
                start_time = time.perf_counter()
                data = obd_sensor.get_obd_data()
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                
                # 使用 logging.info 來印出結構化的數據
                log_message = (f"耗時: {duration_ms:6.1f} ms | RPM: {data.rpm} | Speed: {data.speed} | Temp: {data.coolant_temp} | Volt: {data.battery_voltage} | Load: {data.engine_load}% | Throttle: {data.throttle_pos}%")
                logging.info(log_message)
                
                time.sleep(1.0)

    except KeyboardInterrupt:
        logging.info("使用者手動中斷程式。")
    except Exception as e:
        logging.error(f"測試過程中發生未預期的錯誤: {e}")
    finally:
        logging.info("正在關閉連線...")
        obd_sensor.disconnect()
