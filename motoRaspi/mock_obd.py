# mock_obd.py

import random
import time
from typing import Optional

try:
    from app.models import OBDData
except ImportError:
    print("[FATAL ERROR] 無法匯入 'app.models'。請確保此腳本的執行路徑正確。")
    class OBDData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def __repr__(self): return f"OBDData({self.__dict__})"

class MockOBD:
    """
    一個數據驅動的 OBD-II 模擬器。
    其生成的數據模式和範圍，皆基於 '2025-08-17 18-49-58.csv' 日誌檔案進行校準，
    以提供更貼近真實世界的開發與測試體驗。
    """
    def __init__(self):
        """初始化模擬器的狀態。"""
        # 騎乘狀態: 'IDLE', 'ACCELERATING', 'CRUISING', 'DECELERATING'
        self.ride_state = 'IDLE'
        self.state_timer = time.time()

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

    def _update_ride_state(self):
        """根據計時器隨機切換騎乘狀態，模擬真實的騎乘行為。"""
        if time.time() - self.state_timer > random.uniform(3, 10):
            if self.ride_state == 'IDLE':
                self.ride_state = 'ACCELERATING'
            elif self.ride_state == 'ACCELERATING':
                self.ride_state = 'CRUISING'
            elif self.ride_state == 'CRUISING':
                self.ride_state = random.choice(['DECELERATING', 'ACCELERATING'])
            elif self.ride_state == 'DECELERATING':
                # 減速後可能進入怠速或再次加速
                self.ride_state = 'IDLE' if self.speed < 5 else 'ACCELERATING'
            
            self.state_timer = time.time()
            # print(f"Ride State -> {self.ride_state}") # 用於除錯

    def _generate_data_based_on_state(self):
        """根據當前的騎乘狀態，生成一組有關聯性的模擬數據。"""
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
            # 轉速與時速和油門開度正相關
            self.rpm = self.speed * random.uniform(60, 90) + (self.throttle_pos * 20)
            self.engine_load = min(100, self.engine_load + random.uniform(10, 20))

        elif self.ride_state == 'CRUISING':
            self.speed += random.uniform(-2, 2) # 速度微幅波動
            self.throttle_pos = random.uniform(15.0, 40.0) # 巡航時油門開度較小且穩定
            self.rpm = self.speed * random.uniform(50, 70)
            self.engine_load = random.uniform(30.0, 50.0)

        elif self.ride_state == 'DECELERATING':
            self.speed = max(0, self.speed - random.uniform(5, 10))
            self.throttle_pos = max(0, self.throttle_pos - random.uniform(10, 20)) # 鬆油門
            self.rpm = self.speed * random.uniform(40, 60) + 1500 # 帶檔滑行轉速較高
            self.engine_load = max(10, self.engine_load - random.uniform(5, 15))

        # --- 數據邊界與合理性約束 ---
        self.speed = max(0, min(self.speed, 200))
        self.rpm = max(0, min(self.rpm, 12000)) if self.speed > 0 else random.uniform(1400, 1600)
        self.throttle_pos = max(0, min(self.throttle_pos, 100))
        self.engine_load = max(0, min(self.engine_load, 100))
        
        # --- 更新其他感測器數據 ---
        # 水溫會隨時間緩慢上升至工作溫度
        elapsed_time = time.time() - self.start_time
        if self.coolant_temp < 90:
            self.coolant_temp += elapsed_time * 0.01
        else:
            self.coolant_temp = random.uniform(88.0, 95.0)
        
        # 電壓在引擎運轉時應較高
        self.battery_voltage = random.uniform(13.8, 14.4) if self.rpm > 1000 else 12.6
        
        self.intake_air_temp = self.coolant_temp - random.uniform(30, 40)
        self.intake_map = int(self.engine_load * 0.8 + 20) # 簡化關聯
        self.timing_advance = 10 + (self.rpm / 1000) * 2
        self.short_term_fuel_trim_b1 = random.uniform(-5.0, 5.0)


    def get_obd_data(self) -> OBDData:
        """
        獲取一組模擬的、基於真實日誌數據模式的 OBD-II 數據。
        """
        self._generate_data_based_on_state()

        # 回傳一個包含所有欄位的完整 OBDData 物件
        return OBDData(
            rpm=int(self.rpm),
            speed=int(self.speed),
            coolant_temp=round(self.coolant_temp, 1),
            battery_voltage=round(self.battery_voltage, 2),
            throttle_pos=round(self.throttle_pos, 2),
            engine_load=round(self.engine_load, 2),
            abs_load_val=round(self.engine_load * 0.8, 2), # 簡化模擬
            timing_advance=round(self.timing_advance, 1),
            intake_air_temp=round(self.intake_air_temp, 1),
            intake_map=int(self.intake_map),
            fuel_system_status=self.fuel_system_status,
            short_term_fuel_trim_b1=round(self.short_term_fuel_trim_b1, 2),
            long_term_fuel_trim_b1=self.long_term_fuel_trim_b1,
            o2_sensor_voltage_b1s1=round(self.o2_sensor_voltage_b1s1, 3)
        )

# =================================================================
# --- 獨立執行時的測試區塊 ---
# =================================================================
if __name__ == '__main__':
    print("--- MockOBD 獨立測試模式 (v4.0 - 數據日誌校準版) ---")
    mock_sensor = MockOBD()
    try:
        print("\n--- 開始循環生成數據 (每 500ms 一次)，按 Ctrl+C 結束 ---")
        while True:
            data = mock_sensor.get_obd_data()
            print(
                f"[{time.strftime('%H:%M:%S')}] "
                f"State: {mock_sensor.ride_state.ljust(12)} | "
                f"RPM: {data.rpm:<5} | "
                f"Speed: {data.speed:<3} km/h | "
                f"Throttle: {data.throttle_pos:.1f}% | "
                f"Temp: {data.coolant_temp}°C"
            )
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n使用者手動中斷程式。")

