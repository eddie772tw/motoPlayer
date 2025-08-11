# obd_reader.py

import serial
import time
from typing import Optional

# 專案結構假設:
# /project_root
# ├── obd_reader.py  (此檔案)
# └── /app
#     └── models.py
# 如果執行此檔案時出現 ModuleNotFoundError，
# 請確認您的 Python 環境路徑設定正確，或者將此檔案移動到與 run.py 同層的目錄。
try:
    from app.models import OBDData
except ImportError:
    print("[FATAL ERROR] 無法匯入 'app.models'。請確保此腳本的執行路徑正確。")
    # 提供一個備用的假類別，以便在獨立測試時腳本不會崩潰
    class OBDData:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
        def __repr__(self):
            return f"OBDData({self.__dict__})"

# =================================================================
# --- 常數定義 (Constants) ---
# =================================================================

# ELM327 初始化指令
ELM327_RESET = "ATZ"
ELM327_ECHO_OFF = "ATE0"
ELM327_LINEFEEDS_OFF = "ATL0"
ELM327_AUTO_PROTOCOL = "ATSP0"
ELM327_HEADERS_OFF = "ATH0"

# 標準 OBD-II PID (參數ID)
PID_RPM = "010C"
PID_SPEED = "010D"
PID_COOLANT_TEMP = "0105"
PID_MODULE_VOLTAGE = "0142"

class RealOBD:
    """
    與真實的 ELM327 OBD-II 藍牙適配器進行通訊的類別。
    其設計目標是作為 mock_obd.py 中 MockOBD 類別的「即插即用替代品」。
    """
    def __init__(self, port="/dev/rfcomm0", baudrate=38400, timeout=1):
        """
        初始化 RealOBD 物件。
        :param port: 序列埠的路徑，對應我們用 rfcomm 綁定的裝置。
        :param baudrate: 傳輸速率，38400 是 ELM327 藍牙模組最常見的速率。
        :param timeout: 讀取序列埠的超時時間（秒）。
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None  # serial.Serial 物件將在 connect() 中被建立
        self.is_connected = False

    def connect(self) -> bool:
        """
        建立與 OBD-II 適配器的序列埠連線，並執行初始化指令序列。
        :return: 連線與初始化成功則回傳 True，否則回傳 False。
        """
        print(f"正在嘗試連線到 {self.port}，傳輸速率 {self.baudrate}...")
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            
            # --- 初始化 ELM327 ---
            # 執行一個指令序列來確保適配器處於一個乾淨、可預測的狀態。
            self._send_command(ELM327_RESET, delay_after=1.5) # 重置需要較長的等待時間
            self._send_command(ELM327_ECHO_OFF)         # 關閉回顯，避免收到的數據包含我們發送的指令
            self._send_command(ELM327_LINEFEEDS_OFF)    # 關閉換行，簡化回應解析
            self._send_command(ELM327_AUTO_PROTOCOL)    # 設定為自動搜尋通訊協議
            self._send_command(ELM327_HEADERS_OFF)      # 關閉標頭，我們不需要CAN bus的標頭資訊

            self.is_connected = True
            print("OBD-II 適配器連線並初始化成功！")
            return True
        except serial.SerialException as e:
            print(f"[ERROR] 無法開啟序列埠 {self.port}: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """
        關閉序列埠連線。
        """
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.is_connected = False
        print("OBD-II 連線已關閉。")

    def _send_command(self, command: str, delay_after: float = 0.1) -> str:
        """
        (私有方法) 向 ELM327 發送指令，並讀取、清理、回傳回應。
        :param command: 要發送的指令 (例如 "010C")。
        :param delay_after: 發送指令後等待一小段時間，給予裝置處理時間。
        :return: 清理過的、單行的回應字串。
        """
        if not (self.ser and self.ser.is_open):
            # print("[ERROR] 指令發送失敗：未連線。")
            return "ERROR: NOT CONNECTED"
        
        # 清空輸入與輸出緩衝區，避免讀到舊的數據
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        # ELM327 指令需要以回車符結尾
        full_command = command + '\r'
        self.ser.write(full_command.encode('utf-8'))
        
        # 讀取所有回應行，直到遇到 ELM327 的提示符 '>'
        lines = []
        while True:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if '>' in line: # 提示符代表指令已執行完畢
                    break
                if line: # 僅添加非空行
                    lines.append(line)
            except serial.SerialException:
                print("[ERROR] 讀取序列埠時發生錯誤。")
                return "ERROR: READ FAILED"

        time.sleep(delay_after) # 等待

        # 清理回應：移除指令本身的回顯和空字串
        response = "".join(lines).replace(command, "").strip()
        
        # print(f"CMD: '{command}' -> RAW RSP: '{lines}' -> CLEAN RSP: '{response}'")
        return response

    # --- 數據解析的私有方法 ---

    def _parse_rpm(self, response: str) -> Optional[int]:
        """解析 RPM (010C) 的回應"""
        # 預期的回應格式: 41 0C XX YY
        parts = response.split()
        if len(parts) >= 4 and parts[0] == "41" and parts[1] == "0C":
            try:
                a = int(parts[2], 16)
                b = int(parts[3], 16)
                rpm = ((a * 256) + b) / 4
                return int(rpm)
            except (ValueError, IndexError):
                return None
        return None

    def _parse_speed(self, response: str) -> Optional[int]:
        """解析 Speed (010D) 的回應"""
        # 預期的回應格式: 41 0D XX
        parts = response.split()
        if len(parts) >= 3 and parts[0] == "41" and parts[1] == "0D":
            try:
                speed = int(parts[2], 16)
                return speed
            except (ValueError, IndexError):
                return None
        return None
    
    def _parse_coolant_temp(self, response: str) -> Optional[float]:
        """解析 Coolant Temperature (0105) 的回應"""
        # 預期的回應格式: 41 05 XX
        parts = response.split()
        if len(parts) >= 3 and parts[0] == "41" and parts[1] == "05":
            try:
                temp = int(parts[2], 16) - 40
                return float(temp)
            except (ValueError, IndexError):
                return None
        return None

    def _parse_voltage(self, response: str) -> Optional[float]:
        """解析 Control Module Voltage (0142) 的回應"""
        # 預期的回應格式: 41 42 XX YY
        parts = response.split()
        if len(parts) >= 4 and parts[0] == "41" and parts[1] == "42":
            try:
                a = int(parts[2], 16)
                b = int(parts[3], 16)
                voltage = ((a * 256) + b) / 1000.0
                return round(voltage, 2)
            except (ValueError, IndexError):
                return None
        return None

    def _calculate_gear(self, rpm: Optional[int], speed: Optional[int]) -> Optional[int]:
        """
        根據轉速和時速估算檔位。
        此邏輯直接從 mock_obd.py 移植而來，未來可根據真實數據進行微調。
        """
        if rpm is None or speed is None:
            return None
        
        if speed == 0:
            return 0 # N檔
        
        # 轉速與時速的比值，數字越小檔位越高
        # 這個比值需要根據您的車輛實際情況進行大量測試和微調
        ratio = rpm / speed
        
        if ratio > 85: return 1
        if ratio > 65: return 2
        if ratio > 50: return 3
        if ratio > 40: return 4
        if ratio > 30: return 5
        return 6

    # --- 公開的主要方法 ---

    def get_obd_data(self) -> OBDData:
        """
        (公開方法) 獲取所有車輛數據，並打包成 OBDData 物件。
        這是最終與 Flask App 整合的介面。
        它會依序請求各項數據，解析後回傳一個標準化的物件。
        """
        if not self.is_connected:
            return OBDData() # 如果未連線，回傳一個空的物件

        # 依序獲取並解析各項數據
        rpm_response = self._send_command(PID_RPM)
        rpm = self._parse_rpm(rpm_response)

        speed_response = self._send_command(PID_SPEED)
        speed = self._parse_speed(speed_response)

        temp_response = self._send_command(PID_COOLANT_TEMP)
        coolant_temp = self._parse_coolant_temp(temp_response)

        voltage_response = self._send_command(PID_MODULE_VOLTAGE)
        battery_voltage = self._parse_voltage(voltage_response)

        # 計算檔位
        gear = self._calculate_gear(rpm, speed)

        # 打包成 Pydantic 物件並回傳
        return OBDData(
            rpm=rpm,
            speed=speed,
            coolant_temp=coolant_temp,
            battery_voltage=battery_voltage,
            gear=gear
        )

# =================================================================
# --- 獨立執行時的測試區塊 ---
# =================================================================

if __name__ == '__main__':
    print("--- RealOBD 獨立測試模式 ---")
    
    # 建立 RealOBD 物件
    obd_sensor = RealOBD(port="/dev/rfcomm0")
    
    try:
        # 嘗試連線
        if obd_sensor.connect():
            print("\n--- 開始循環讀取數據 (每2秒一次)，按 Ctrl+C 結束 ---")
            
            # 循環讀取數據
            while True:
                data = obd_sensor.get_obd_data()
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {data}")
                time.sleep(2)

    except KeyboardInterrupt:
        print("\n使用者手動中斷程式。")
    except Exception as e:
        print(f"\n發生未預期的錯誤: {e}")
    finally:
        # 無論如何，最後都要確保連線被關閉
        print("正在關閉連線...")
        obd_sensor.disconnect()

