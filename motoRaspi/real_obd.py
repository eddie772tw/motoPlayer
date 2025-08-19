# real_obd.py (BLE Refactored)
#
# 版本: 5.1 Performance Test
# 描述: 此版本已從傳統藍牙序列埠 (pyserial) 徹底重構為低功耗藍牙 (BLE) 通訊。
#      它使用 bleak 函式庫來與 ELM327 BLE 適配器進行非同步通訊，
#      同時保留了所有原始的 ELM327 指令集和數據解析邏輯。
#      獨立測試區塊已增強，可測量每次輪詢的耗時以驗證性能。

import asyncio
import time
from typing import Optional, Dict
from bleak import BleakClient, BleakError

# --- Pydantic 模型模擬 ---
# 在獨立執行時，若無法從 app.models 導入，則建立一個模擬的 OBDData 類別以便測試。
try:
    from app.models import OBDData
except ImportError:
    print("[WARNING] 無法匯入 'app.models'。將使用內部模擬的 OBDData 類別。")
    class OBDData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def __repr__(self): return f"OBDData({self.__dict__})"

# =================================================================
# --- BLE & ELM327 常數定義 ---
# =================================================================

# TODO: 請務必根據您的 nRF Connect 掃描結果，填寫以下 BLE 參數
OBD_BLE_ADDRESS = "66:1E:32:8A:55:2C"  # ELM327 適配器的 MAC 位址
# 用於寫入指令 (AT, PID) 到 ELM327 的特徵 UUID (通常稱為 TX 或 Write)
UART_TX_CHAR_UUID = "0000fff2-0000-1000-8000-00805f9b34fb" # 假設值，請替換
# 用於接收 ELM327 回應數據的特徵 UUID (通常稱為 RX 或 Notify)
UART_RX_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb" # 假設值，請替換

# ELM327 初始化指令
ELM327_INIT_COMMANDS: Dict[str, float] = {
    "ATZ": 1.5,      # 重置 ELM327
    "ATE0": 0.1,     # 關閉指令回顯 (Echo Off)
    "ATL0": 0.1,     # 關閉換行 (Linefeeds Off)
    "ATH0": 0.1,     # 關閉標頭 (Headers Off)
    "ATSP0": 0.1,    # 自動偵測協議
}

# 核心 PID (Parameter IDs)
PID_RPM = "010C"
PID_SPEED = "010D"
PID_COOLANT_TEMP = "0105"
PID_MODULE_VOLTAGE = "0142"

class RealOBD:
    """
    透過 BLE 與真實的 ELM327 OBD-II 適配器進行非同步通訊的類別。
    """
    def __init__(self, device_address: str):
        self.device_address = device_address
        self.client: Optional[BleakClient] = None
        self.is_connected: bool = False
        self.response_queue: asyncio.Queue = asyncio.Queue()
        self.buffer = ""

    async def connect(self) -> bool:
        """
        建立與 OBD-II 適配器的 BLE 連線，啟用通知，並執行初始化指令序列。
        """
        print(f"正在嘗試連線到 BLE 適配器: {self.device_address}...")
        try:
            self.client = BleakClient(self.device_address)
            await self.client.connect()

            # 啟用來自 RX 特徵的通知
            await self.client.start_notify(UART_RX_CHAR_UUID, self._notification_handler)
            print(f"已成功連線並啟用對特徵 {UART_RX_CHAR_UUID} 的通知。")
            
            # 執行初始化指令
            print("正在初始化 ELM327...")
            for cmd, delay in ELM327_INIT_COMMANDS.items():
                response = await self._send_command(cmd, timeout=2.0)
                print(f"  > {cmd}... {response}")
                await asyncio.sleep(delay)

            self.is_connected = True
            print("OBD-II 適配器 (BLE) 連線並初始化成功！")
            return True
        except (BleakError, asyncio.TimeoutError) as e:
            print(f"[ERROR] BLE 連線或初始化失敗: {e}")
            self.is_connected = False
            return False

    async def disconnect(self):
        """
        中斷 BLE 連線。
        """
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        self.is_connected = False
        print("OBD-II (BLE) 連線已關閉。")

    def _notification_handler(self, sender: int, data: bytearray):
        """
        (回呼函式) 處理從 BLE 特徵收到的通知數據。
        """
        decoded_data = data.decode('utf-8', errors='ignore')
        # ELM327 的回應通常以 '>' 結尾，我們以此作為一個完整數據包的標誌
        self.buffer += decoded_data
        if '>' in self.buffer:
            # 將完整的回應放入佇列
            self.response_queue.put_nowait(self.buffer.strip())
            self.buffer = ""

    async def _send_command(self, command: str, timeout: float = 1.0) -> str:
        """
        (私有方法) 發送指令到 TX 特徵，並等待來自通知佇列的回應。
        """
        if not self.is_connected or not self.client:
            return "ERROR: NOT CONNECTED"

        # 清空佇列，確保只接收本次指令的回應
        while not self.response_queue.empty():
            self.response_queue.get_nowait()

        # 發送指令 (必須以 '\r' 結尾)
        await self.client.write_gatt_char(UART_TX_CHAR_UUID, (command + '\r').encode('utf-8'))

        try:
            # 等待來自 _notification_handler 的回應
            response = await asyncio.wait_for(self.response_queue.get(), timeout)
            # 清理回應字串，移除原始指令和結尾的 '>'
            cleaned_response = response.replace(command, "").replace(">", "").strip()
            return cleaned_response
        except asyncio.TimeoutError:
            return f"ERROR: CMD '{command}' TIMEOUT"

    # --- 數據解析的私有方法 (與原版完全相同) ---
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
    async def get_obd_data(self) -> OBDData:
        """
        (非同步) 獲取核心儀表板數據，並打包成 OBDData 物件。
        """
        if not self.is_connected:
            return OBDData()

        # 依序獲取並解析核心數據
        rpm_response = await self._send_command(PID_RPM)
        speed_response = await self._send_command(PID_SPEED)
        temp_response = await self._send_command(PID_COOLANT_TEMP)
        volt_response = await self._send_command(PID_MODULE_VOLTAGE)

        rpm = self._parse_rpm(rpm_response)
        speed = self._parse_speed(speed_response)
        coolant_temp = self._parse_coolant_temp(temp_response)
        battery_voltage = self._parse_voltage(volt_response)

        return OBDData(
            rpm=rpm,
            speed=speed,
            coolant_temp=coolant_temp,
            battery_voltage=battery_voltage,
        )

# =================================================================
# --- 獨立執行時的非同步測試區塊 (含性能測量) ---
# =================================================================
async def main_test():
    """
    用於獨立測試此模組的非同步主函式，並測量每次數據輪詢的耗時。
    """
    print("--- RealOBD (BLE) 獨立性能測試模式 ---")
    TARGET_HZ = 5
    TARGET_MS = 1000 / TARGET_HZ
    
    obd_sensor = RealOBD(device_address=OBD_BLE_ADDRESS)
    try:
        if await obd_sensor.connect():
            print(f"\n--- 開始循環讀取數據 (目標: {TARGET_HZ} Hz / {TARGET_MS:.0f} ms)，按 Ctrl+C 結束 ---")
            
            total_time = 0
            successful_polls = 0

            for i in range(30): # 進行 30 次輪詢測試
                start_time = time.perf_counter()
                
                data = await obd_sensor.get_obd_data()
                
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                
                # 檢查數據是否有效
                if data.rpm is not None or data.speed is not None:
                    successful_polls += 1
                    total_time += duration_ms

                # 根據耗時決定狀態顯示
                status = "✅ OK" if duration_ms <= TARGET_MS else "⚠️ SLOW"
                
                print(
                    f"輪詢 #{i+1:02d}: "
                    f"耗時: {duration_ms:6.1f} ms [{status}] | "
                    f"RPM: {data.rpm}, Speed: {data.speed}, "
                    f"Temp: {data.coolant_temp}, Voltage: {data.battery_voltage}"
                )
                
                # 為了不讓連續請求過於頻繁，在每次輪詢後稍微等待
                await asyncio.sleep(0.3)
            
            # 測試結束後印出統計數據
            if successful_polls > 0:
                average_time = total_time / successful_polls
                print("\n--- 測試總結 ---")
                print(f"成功輪詢次數: {successful_polls} / 30")
                print(f"平均輪詢耗時: {average_time:.1f} ms")
                if average_time <= TARGET_MS:
                    print(f"性能表現: ✅ 達標 (平均低於 {TARGET_MS:.0f} ms)")
                else:
                    print(f"性能表現: ❌ 未達標 (平均高於 {TARGET_MS:.0f} ms)")

    except Exception as e:
        print(f"測試過程中發生錯誤: {e}")
    finally:
        print("正在關閉連線...")
        await obd_sensor.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main_test())
    except KeyboardInterrupt:
        print("\n使用者手動中斷程式。")
