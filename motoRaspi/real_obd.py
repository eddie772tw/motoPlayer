# real_obd.py

import serial
import time
from typing import Optional

try:
    from app.models import OBDData
except ImportError:
    print("[FATAL ERROR] 無法匯入 'app.models'。請確保此腳本的執行路徑正確。")
    class OBDData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def __repr__(self): return f"OBDData({self.__dict__})"

# =================================================================
# --- 常數定義 (Constants) ---
# =================================================================

# ELM327 初始化指令
ELM327_RESET = "ATZ"
ELM327_ECHO_OFF = "ATE0"
ELM327_LINEFEEDS_OFF = "ATL0"
ELM327_AUTO_PROTOCOL = "ATSP0"
ELM327_HEADERS_OFF = "ATH0"

# 我們將要主動獲取的核心 PID
PID_RPM = "010C"
PID_SPEED = "010D"
PID_COOLANT_TEMP = "0105"
PID_MODULE_VOLTAGE = "0142"

# 其他未來可能用到的 PID (暫不使用)
# PID_THROTTLE_POS = "0111"
# PID_ENGINE_LOAD = "0104"
# ...

class RealOBD:
    """
    與真實的 ELM327 OBD-II 藍牙適配器進行通訊的類別。
    此版本已簡化，專注於獲取核心儀表板數據。
    """
    def __init__(self, port="/dev/rfcomm0", baudrate=38400, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.is_connected = False

    def connect(self) -> bool:
        """
        建立與 OBD-II 適配器的序列埠連線，並執行初始化。
        """
        print(f"正在嘗試連線到 {self.port}...")
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            
            self._send_command(ELM327_RESET, delay_after=1.5)
            self._send_command(ELM327_ECHO_OFF)
            self._send_command(ELM327_LINEFEEDS_OFF)
            self._send_command(ELM327_AUTO_PROTOCOL)
            self._send_command(ELM327_HEADERS_OFF)

            self.is_connected = True
            print("OBD-II 適配器連線並初始化成功！")
            return True
        except serial.SerialException as e:
            print(f"[ERROR] 無法開啟序列埠 {self.port}: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.is_connected = False
        print("OBD-II 連線已關閉。")

    def _send_command(self, command: str, delay_after: float = 0.05) -> str:
        """
        (私有方法) 發送指令並讀取回應。
        """
        if not (self.ser and self.ser.is_open):
            return "ERROR: NOT CONNECTED"
        
        self.ser.reset_input_buffer()
        self.ser.write((command + '\r').encode('utf-8'))
        
        lines = []
        while True:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if '>' in line:
                    break
                if line:
                    lines.append(line)
            except serial.SerialException:
                return "ERROR: READ FAILED"

        time.sleep(delay_after)
        response = "".join(lines).replace(command, "").strip()
        return response

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
        parts = response.split()
        if len(parts) >= 4 and parts[0] == "41" and parts[1] == "42":
            try: return round(((int(parts[2], 16) * 256) + int(parts[3], 16)) / 1000.0, 2)
            except: return None
        return None

    # --- 公開的主要方法 ---
    def get_obd_data(self) -> OBDData:
        """
        獲取核心儀表板數據，並打包成一個完整的 (但大部分為空) OBDData 物件。
        """
        if not self.is_connected:
            return OBDData()

        # 依序獲取並解析核心數據
        rpm = self._parse_rpm(self._send_command(PID_RPM))
        speed = self._parse_speed(self._send_command(PID_SPEED))
        coolant_temp = self._parse_coolant_temp(self._send_command(PID_COOLANT_TEMP))
        battery_voltage = self._parse_voltage(self._send_command(PID_MODULE_VOLTAGE))

        # 回傳 Pydantic 物件，未提供的欄位將自動為 None
        return OBDData(
            rpm=rpm,
            speed=speed,
            coolant_temp=coolant_temp,
            battery_voltage=battery_voltage,
        )

# =================================================================
# --- 獨立執行時的測試區塊 ---
# =================================================================
if __name__ == '__main__':
    print("--- RealOBD 獨立測試模式 (v4.0 簡化版) ---")
    obd_sensor = RealOBD(port="/dev/rfcomm0")
    try:
        if obd_sensor.connect():
            print("\n--- 開始循環讀取數據 (每秒一次)，按 Ctrl+C 結束 ---")
            while True:
                data = obd_sensor.get_obd_data()
                print(f"[{time.strftime('%H:%M:%S')}] RPM: {data.rpm}, Speed: {data.speed}, Temp: {data.coolant_temp}, Voltage: {data.battery_voltage}")
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n使用者手動中斷程式。")
    finally:
        print("正在關閉連線...")
        obd_sensor.disconnect()
