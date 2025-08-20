# real_obd.py (RFCOMM Final)
#
# 版本: 6.1 (Standalone Testable)
# 描述: 此版本已從 BLE 方案切換回更穩定的傳統藍牙 RFCOMM Socket 方案。
#      它使用 PyBluez 函式庫直接建立連線，並在初始化時執行
#      一套完整的診斷與協議設定指令，以確保與 ECU 的穩定通訊。
#      [NEW] 新增了 if __name__ == '__main__' 區塊，使此檔案可獨立執行以進行測試。

import bluetooth
import time
from typing import Optional
import logging

try:
    from app.models import OBDData
except ImportError:
    print("[WARNING] 無法匯入 'app.models'。將使用內部模擬的 OBDData 類別。")
    class OBDData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def __repr__(self): return f"OBDData({self.__dict__})"

# =================================================================
# ---               ELM327 指令集 (Constants)                   ---
# =================================================================

# 關鍵初始化指令序列
ELM327_INIT_SEQUENCE = [
    "ATZ",          # 重置 ELM327
    "ATE0",         # 關閉指令回顯
    "ATL0",         # 關閉換行
    "ATH0",         # 關閉標頭
    "ATSP5",        # 強制使用協議 5: ISO 14230-4 KWP (fast init)
]

# 核心 PID (Parameter IDs)
PID_RPM = "010C"
PID_SPEED = "010D"
PID_COOLANT_TEMP = "0105"
PID_MODULE_VOLTAGE = "ATRV" # 使用 AT 指令直接讀取電壓更可靠

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
        """
        建立與 OBD-II 適配器的 RFCOMM Socket 連線，並執行初始化序列。
        """
        logging.info(f"正在嘗試連線到 {self.mac_address} 的 RFCOMM 頻道 {self.channel}...")
        try:
            self.sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.sock.connect((self.mac_address, self.channel))
            self.sock.settimeout(5.0)
            logging.info("RFCOMM Socket 連線成功！")

            # 執行初始化序列
            logging.info("正在執行 ELM327 初始化序列...")
            for cmd in ELM327_INIT_SEQUENCE:
                response = self._send_command(cmd)
                print(f"  > {cmd:<5}... {response.splitlines()[0]}")
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
            logging.error(f"[!] 連線或初始化失敗: {e}")
            self.disconnect()
            return False

    def disconnect(self):
        """關閉 Socket 連線。"""
        if self.sock:
            self.sock.close()
        self.sock = None
        self.is_connected = False
        logging.warning("OBD-II (RFCOMM) 連線已關閉。")

    def _send_command(self, command: str) -> str:
        """(私有方法) 發送指令並接收完整的回應。"""
        if not self.sock:
            return "ERROR: NOT CONNECTED"
        
        # 清空接收緩衝區
        try:
            while self.sock.recv(1024): pass
        except bluetooth.btcommon.BluetoothError:
            pass # 忽略超時，因為緩衝區可能本來就是空的

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

    # --- 數據解析的私有方法 ---
    def _parse_rpm(self, response: str) -> Optional[int]:
        parts = response.split()
        if len(parts) >= 4 and parts[0] == "41" and parts[1] == "0C":
            try: return int(((int(parts[2], 16) * 256) + int(parts[3], 16)) / 4)
            except: return None
        return None

    def _parse_speed(self, response: str) -> Optional[int]:
        parts = response.split()
        if len(parts) >= 3 and parts[0] == "41" and parts[1] == "0D":
            try: return int(parts[2], 16)
            except: return None
        return None
    
    def _parse_coolant_temp(self, response: str) -> Optional[float]:
        parts = response.split()
        if len(parts) >= 3 and parts[0] == "41" and parts[1] == "05":
            try: return float(int(parts[2], 16) - 40)
            except: return None
        return None

    def _parse_voltage(self, response: str) -> Optional[float]:
        try:
            return float(response.replace("V", ""))
        except:
            return None

    # --- 公開的主要方法 ---
    def get_obd_data(self) -> OBDData:
        """獲取核心儀表板數據，並打包成 OBDData 物件。"""
        if not self.is_connected:
            return OBDData()

        rpm = self._parse_rpm(self._send_command(PID_RPM))
        speed = self._parse_speed(self._send_command(PID_SPEED))
        coolant_temp = self._parse_coolant_temp(self._send_command(PID_COOLANT_TEMP))
        battery_voltage = self._parse_voltage(self._send_command(PID_MODULE_VOLTAGE))

        return OBDData(
            rpm=rpm,
            speed=speed,
            coolant_temp=coolant_temp,
            battery_voltage=battery_voltage,
        )

# =================================================================
# ---               獨立執行時的測試區塊                          ---
# =================================================================
if __name__ == '__main__':
    # 當此檔案被直接執行時，會運行以下測試程式碼。
    # 這讓我們可以在不啟動完整 Web 伺服器的情況下，快速測試 OBD 連線。
    
    # --- 測試用的設定 ---
    # 請在此處填寫您的 OBD 適配器 MAC 位址
    TEST_DEVICE_ADDRESS = "66:1E:32:8A:55:2C"
    
    print("--- RealOBD (RFCOMM) 獨立測試模式 ---")
    
    # 建立 RealOBD 物件
    obd_sensor = RealOBD(mac_address=TEST_DEVICE_ADDRESS)
    
    try:
        # 嘗試連線並初始化
        if obd_sensor.connect():
            print("\n--- 開始循環讀取數據 (每秒一次)，按 Ctrl+C 結束 ---")
            while True:
                start_time = time.perf_counter()
                
                # 獲取數據
                data = obd_sensor.get_obd_data()
                
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                
                # 印出結果
                print(
                    f"[{time.strftime('%H:%M:%S')}] "
                    f"輪詢耗時: {duration_ms:6.1f} ms | "
                    f"RPM: {data.rpm}, Speed: {data.speed}, "
                    f"Temp: {data.coolant_temp}, Voltage: {data.battery_voltage}"
                )
                
                # 控制輪詢頻率
                time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n使用者手動中斷程式。")
    except Exception as e:
        print(f"\n測試過程中發生未預期的錯誤: {e}")
    finally:
        print("正在關閉連線...")
        obd_sensor.disconnect()

