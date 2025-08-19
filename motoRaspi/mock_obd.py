# mock_obd.py (Asynchronous Refactored)
#
# 版本: 5.0 Async
# 描述: 此版本已從同步類別重構為非同步類別，以匹配 real_obd.py (BLE版) 的非同步介面。
#      這確保了開發者可以在真實與模擬 OBD 環境之間無縫切換，以利於除錯。

import asyncio
import random
import time
from typing import Optional

# --- Pydantic 模型模擬 ---
try:
    from app.models import OBDData
except ImportError:
    print("[WARNING] 無法匯入 'app.models'。將使用內部模擬的 OBDData 類別。")
    class OBDData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def __repr__(self): return f"OBDData({self.__dict__})"

class MockOBD:
    """
    一個數據驅動的、非同步的 OBD-II 模擬器。
    其生成的數據模式和範圍，皆基於真實日誌檔案進行校準，
    並提供與 RealOBD (BLE版) 完全一致的非同步方法。
    """
    def __init__(self):
        """初始化模擬器的狀態。"""
        # 騎乘狀態: 'IDLE', 'ACCELERATING', 'CRUISING', 'DECELERATING'
        self.ride_state = 'IDLE'
        self.state_timer = time.time()
        self.is_connected = False

        # 核心數據，初始值模擬冷車啟動
        self.rpm = 1500
        self.speed = 0
        self.coolant_temp = 45.0
        self.battery_voltage = 12.6
        self.throttle_pos = 3.0
        self.engine_load = 15.0
        
        # 其他感測器數據
        self.abs_load_val = 10.0
        self.timing_advance = 8.0
        self.intake_air_temp = 35.0
        self.intake_map = 30
        self.fuel_system_status = "Closed loop"
        self.short_term_fuel_trim_b1 = 0.0
        self.long_term_fuel_trim_b1 = 0.0
        self.o2_sensor_voltage_b1s1 = 0.5

        self.start_time = time.time()

    async def connect(self) -> bool:
        """
        (非同步) 模擬連線過程。
        """
        print("正在模擬連線到 OBD-II 適配器...")
        await asyncio.sleep(0.1) # 模擬網路延遲
        self.is_connected = True
        print("模擬 OBD-II 適配器連線成功！")
        return True

    async def disconnect(self):
        """
        (非同步) 模擬中斷連線。
        """
        self.is_connected = False
        print("模擬 OBD-II 連線已關閉。")
        await asyncio.sleep(0.05)

    def _update_ride_state(self):
        """(同步) 根據計時器隨機切換騎乘狀態，模擬真實的騎乘行為。"""
        if time.time() - self.state_timer > random.uniform(3, 10):
            if self.ride_state == 'IDLE':
                self.ride_state = 'ACCELERATING'
            elif self.ride_state == 'ACCELERATING':
                self.ride_state = 'CRUISING'
            elif self.ride_state == 'CRUISING':
                self.ride_state = random.choice(['DECELERATING', 'ACCELERATING'])
            elif self.ride_state == 'DECELERATING':
                self.ride_state = 'IDLE' if self.speed < 5 else 'ACCELERATING'
            
            self.state_timer = time.time()

    def _generate_data_based_on_state(self):
        """(同步) 根據當前的騎乘狀態，生成一組有關聯性的模擬數據。"""
        self._update_ride_state()

        # --- 根據狀態更新核心數據 ---
        if self.ride_state == 'IDLE':
            self.speed = max(0, self.speed - random.uniform(1, 5))
            self.rpm = random.uniform(1400, 1600)
            self.throttle_pos = random.uniform(2.0, 5.0)
            self.engine_load = random.uniform(15.0, 25.0)
        
        elif self.ride_state == 'ACCELERATING':
            self.speed += random.uniform(2, 8)
            self.throttle_pos = min(100, self.throttle_pos + random.uniform(5, 15))
            self.rpm = self.speed * random.uniform(60, 90) + (self.throttle_pos * 20)
            self.engine_load = min(100, self.engine_load + random.uniform(10, 20))

        elif self.ride_state == 'CRUISING':
            self.speed += random.uniform(-2, 2)
            self.throttle_pos = random.uniform(15.0, 40.0)
            self.rpm = self.speed * random.uniform(50, 70)
            self.engine_load = random.uniform(30.0, 50.0)

        elif self.ride_state == 'DECELERATING':
            self.speed = max(0, self.speed - random.uniform(5, 10))
            self.throttle_pos = max(0, self.throttle_pos - random.uniform(10, 20))
            self.rpm = self.speed * random.uniform(40, 60) + 1500
            self.engine_load = max(10, self.engine_load - random.uniform(5, 15))

        # --- 數據邊界與合理性約束 ---
        self.speed = max(0, min(self.speed, 200))
        self.rpm = max(0, min(self.rpm, 12000)) if self.speed > 0 else random.uniform(1400, 1600)
        self.throttle_pos = max(0, min(self.throttle_pos, 100))
        self.engine_load = max(0, min(self.engine_load, 100))
        
        # --- 更新其他感測器數據 ---
        elapsed_time = time.time() - self.start_time
        if self.coolant_temp < 90:
            self.coolant_temp += elapsed_time * 0.01
        else:
            self.coolant_temp = random.uniform(88.0, 95.0)
        
        self.battery_voltage = random.uniform(13.8, 14.4) if self.rpm > 1000 else 12.6
        self.intake_air_temp = self.coolant_temp - random.uniform(30, 40)
        self.intake_map = int(self.engine_load * 0.8 + 20)
        self.timing_advance = 10 + (self.rpm / 1000) * 2
        self.short_term_fuel_trim_b1 = random.uniform(-5.0, 5.0)

    async def get_obd_data(self) -> OBDData:
        """
        (非同步) 獲取一組模擬的、基於真實日誌數據模式的 OBD-II 數據。
        """
        if not self.is_connected:
            return OBDData()

        # 模擬非同步 I/O 操作的延遲
        await asyncio.sleep(0.01) 
        
        self._generate_data_based_on_state()

        # 回傳一個包含所有欄位的完整 OBDData 物件
        return OBDData(
            rpm=int(self.rpm),
            speed=int(self.speed),
            coolant_temp=round(self.coolant_temp, 1),
            battery_voltage=round(self.battery_voltage, 2),
            throttle_pos=round(self.throttle_pos, 2),
            engine_load=round(self.engine_load, 2),
            abs_load_val=round(self.engine_load * 0.8, 2),
            timing_advance=round(self.timing_advance, 1),
            intake_air_temp=round(self.intake_air_temp, 1),
            intake_map=int(self.intake_map),
            fuel_system_status=self.fuel_system_status,
            short_term_fuel_trim_b1=round(self.short_term_fuel_trim_b1, 2),
            long_term_fuel_trim_b1=self.long_term_fuel_trim_b1,
            o2_sensor_voltage_b1s1=round(self.o2_sensor_voltage_b1s1, 3)
        )

# =================================================================
# --- 獨立執行時的非同步測試區塊 ---
# =================================================================
async def main_test():
    """
    用於獨立測試此模組的非同步主函式。
    """
    print("--- MockOBD (Async) 獨立測試模式 ---")
    mock_sensor = MockOBD()
    try:
        if await mock_sensor.connect():
            print("\n--- 開始循環生成數據 (每 500ms 一次)，按 Ctrl+C 結束 ---")
            while True:
                data = await mock_sensor.get_obd_data()
                print(
                    f"[{time.strftime('%H:%M:%S')}] "
                    f"State: {mock_sensor.ride_state.ljust(12)} | "
                    f"RPM: {data.rpm:<5} | "
                    f"Speed: {data.speed:<3} km/h | "
                    f"Throttle: {data.throttle_pos:.1f}% | "
                    f"Temp: {data.coolant_temp}°C"
                )
                await asyncio.sleep(0.5)
    except Exception as e:
        print(f"測試過程中發生錯誤: {e}")
    finally:
        await mock_sensor.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main_test())
    except KeyboardInterrupt:
        print("\n使用者手動中斷程式。")
