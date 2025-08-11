# mock_obd.py (根據 YZF-R15 檔位對照表優化，並強化換檔頻率的版本)

import random
import time
from app.models import OBDData 

class MockOBD:
    """
    模擬機車OBD-II數據的類別。
    此類別會模擬速度、RPM、冷卻液溫度、電池電壓和檔位等數據，
    並特別加入了手動檔機車的檔位與RPM聯動邏輯，參考YZF-R15的特性。
    """
    def __init__(self):
        """
        初始化模擬OBD感測器的狀態變數。
        """
        self.speed = 0  # 速度，單位 km/h
        self.rpm = 800  # 引擎轉速，單位 RPM
        self.coolant_temp = 25.0  # 冷卻液溫度，單位 攝氏度
        self.battery_voltage = 12.6  # 電池電壓，單位 伏特
        self.last_update_time = time.time()  # 上次數據更新的時間戳

        # --- 檔位相關變數與設定 ---
        self.current_gear = 0  # 當前檔位 (0: 空檔/停止, 1-6: 實際檔位)
        self.gear_change_cooldown = 0.0 # 避免頻繁換檔的冷卻時間 (秒)

        # 根據 YZF-R15 檔位、RPM 與速度大致對照表調整係數和範圍
        # 這些係數是根據表格中的速度區間和RPM範圍推算出的平均值，可進一步微調。
        self.GEAR_RPM_PER_KPH = { 
            0: (800, 1200), # 空檔或停止時的RPM範圍，保持不變
            1: 2000 / 10,   # 1檔: 約 200 RPM/km/h (取中間值 2000-8000 RPM / 0-25 km/h)
            2: 3000 / 20,   # 2檔: 約 150 RPM/km/h
            3: 4000 / 35,   # 3檔: 約 114 RPM/km/h
            4: 4500 / 50,   # 4檔: 約 90 RPM/km/h
            5: 5000 / 70,   # 5檔: 約 71 RPM/km/h
            6: 5500 / 90    # 6檔: 約 61 RPM/km/h
        }
        
        # 根據 YZF-R15 對照表中的 RPM 範圍調整閾值
        self.UPSHIFT_RPM_THRESHOLD = 8000  # 高於此RPM時考慮升檔
        self.DOWNSHIFT_RPM_THRESHOLD = 3500 # 低於此RPM時考慮降檔 (稍微提高以鼓勵更早降檔)

        # 引擎轉速的最低和最高限制 (根據 YZF-R15 對照表調整)
        self.MIN_RPM_OPERATING = 2000 # 引擎有速度時的最低操作RPM (參考1檔最低RPM)
        self.MAX_RPM = 10500 # 最高RPM限制 (參考6檔最高RPM)

        # RPM 平滑過渡的係數 (0.0 - 1.0)，數值越大，RPM 變化越快
        self.RPM_SMOOTHING_FACTOR = 0.25 # 稍微加快RPM響應速度，使變化更容易發生

        # 根據 YZF-R15 對照表調整速度區間，用於輔助換檔判斷
        self.GEAR_SPEED_RANGES = {
            1: (0, 25),
            2: (10, 50),
            3: (25, 80),
            4: (40, 100),
            5: (60, 120),
            6: (80, 150) # 稍微擴大6檔上限以匹配模擬最高速度
        }

    def _update_values(self):
        """
        根據時間差和當前狀態更新模擬的OBD數據。
        包含速度、RPM、冷卻液溫度和電池電壓的更新邏輯。
        """
        current_time = time.time()
        time_diff = current_time - self.last_update_time
        self.last_update_time = current_time

        # --- RPM 和檔位計算邏輯 ---
        if self.speed == 0:
            # 速度為0時，強制設為空檔，RPM在怠速範圍內
            self.current_gear = 0
            self.rpm = random.randint(self.GEAR_RPM_PER_KPH[0][0], self.GEAR_RPM_PER_KPH[0][1])
        else:
            # 處理從靜止啟動或空檔滑行時自動切換到1檔
            if self.current_gear == 0:
                self.current_gear = 1 # 假設從靜止啟動或空檔有速度時，自動進入1檔
                print(f"DEBUG: Auto-shifted to 1st gear at Speed: {self.speed} km/h")

            # 根據當前檔位和速度計算目標RPM
            # 確保檔位在有效範圍內
            gear_ratio = self.GEAR_RPM_PER_KPH.get(self.current_gear, self.GEAR_RPM_PER_KPH[1])
            target_rpm = gear_ratio * self.speed

            # 讓RPM平滑接近目標值，避免瞬跳
            self.rpm += (target_rpm - self.rpm) * self.RPM_SMOOTHING_FACTOR
            self.rpm = int(self.rpm)

            # 確保RPM在合理範圍內，特別是行駛中的最低RPM
            if self.rpm < self.MIN_RPM_OPERATING: 
                self.rpm = self.MIN_RPM_OPERATING
            if self.rpm > self.MAX_RPM: 
                self.rpm = self.MAX_RPM

            # --- 模擬自動換檔邏輯 (避免頻繁換檔) ---
            if self.gear_change_cooldown > 0:
                self.gear_change_cooldown -= time_diff
                if self.gear_change_cooldown < 0: self.gear_change_cooldown = 0.0
            
            if self.gear_change_cooldown == 0:
                # 升檔判斷:
                # 1. RPM高於升檔閾值
                # 2. 未達最高檔 (6檔)
                # 3. 當前速度已進入下一檔位的建議速度區間
                next_gear = self.current_gear + 1
                if (self.rpm > self.UPSHIFT_RPM_THRESHOLD and 
                    self.current_gear < 6 and
                    # 確保速度達到下一檔位最低建議速度 (或接近)
                    self.speed >= self.GEAR_SPEED_RANGES.get(next_gear, (0,0))[0] - 5): # 增加5 km/h 的緩衝，讓升檔更容易發生
                    
                    self.current_gear = next_gear
                    print(f"DEBUG: Upshifted to {self.current_gear} gear at Speed: {self.speed} km/h, Current RPM: {self.rpm}")
                    # 升檔瞬間RPM會下降，模擬離合器操作
                    self.rpm = int(self.rpm * 0.7) # 模擬RPM下降約30%
                    self.gear_change_cooldown = 0.8 # 設定0.8秒冷卻時間，讓換檔更頻繁

                # 降檔判斷:
                # 1. RPM低於降檔閾值
                # 2. 未達最低操作檔 (1檔)
                # 3. 當前速度已低於當前檔位的建議速度區間下限 (或接近前一檔位的上限)
                prev_gear = self.current_gear - 1
                if (self.rpm < self.DOWNSHIFT_RPM_THRESHOLD and 
                    self.current_gear > 1 and
                    # 判斷速度是否更適合前一個檔位 (速度低於當前檔位下限 + 緩衝)
                    self.speed < self.GEAR_SPEED_RANGES.get(self.current_gear, (0,0))[0] + 10): # 增加10 km/h 緩衝，讓降檔更容易發生
                    
                    self.current_gear = prev_gear
                    print(f"DEBUG: Downshifted to {self.current_gear} gear at Speed: {self.speed} km/h, Current RPM: {self.rpm}")
                    # 降檔瞬間RPM會上升 (模擬引擎煞車或補油)
                    self.rpm = int(self.rpm * 1.2) # 模擬RPM上升約20%
                    self.gear_change_cooldown = 0.8 # 設定0.8秒冷卻時間，讓換檔更頻繁
                # 特殊降檔情況: 速度非常低時強制降到1檔 (例如，從高速減速到停止前)
                elif self.speed < 15 and self.current_gear > 1:
                    self.current_gear = 1
                    print(f"DEBUG: Forced Downshift to 1st gear due to low speed ({self.speed} km/h)")
                    self.rpm = int(self.rpm * 1.5) # 模擬RPM較大上升
                    self.gear_change_cooldown = 0.8


        # 冷卻液溫度模擬
        # 模擬溫度緩慢上升至工作溫度範圍，然後在該範圍內波動
        if self.coolant_temp < 85.0:
            self.coolant_temp += 1.5 * time_diff
        else:
            self.coolant_temp = random.uniform(85.0, 92.0)
        
        # 電池電壓模擬
        # 模擬引擎運轉時的充電電壓波動
        self.battery_voltage = random.uniform(13.6, 14.1)

    def _calculate_gear(self):
        """
        回傳當前模擬的檔位。
        注意：檔位邏輯已內化到 _update_values 中，此函式僅回傳狀態。
        """
        return self.current_gear

    def get_obd_data(self) -> OBDData:
        """
        獲取模擬的OBD-II數據。
        此函式會更新內部狀態，然後回傳一個包含最新數據的 OBDData 物件。
        """
        # 模擬速度變化
        # 速度變化值，包含加速、減速和保持不變的選項
        # 擴大隨機速度變化範圍，讓速度變化更容易發生
        speed_change = random.choice([-20, -15, -10, -5, 0, 0, 5, 10, 15, 20, 25])
        self.speed += speed_change
        
        # 限制速度在合理範圍內
        if self.speed < 0: self.speed = 0
        if self.speed > 150: self.speed = 150 # 最高速度限制 (略高於6檔上限)

        # 更新所有模擬數據
        self._update_values()
        
        # 建立並回傳 Pydantic 物件
        return OBDData(
            rpm=self.rpm,
            speed=self.speed,
            coolant_temp=round(self.coolant_temp, 1),
            battery_voltage=round(self.battery_voltage, 2),
            gear=self._calculate_gear()
        )

# 獨立測試區塊 (僅在直接運行此檔案時執行)
if __name__ == '__main__':
    mock_obd_sensor = MockOBD()
    print("--- 正在測試 Mock OBD-II 數據生成 (Pydantic Model) ---")
    print("觀察速度、檔位和RPM的聯動變化，以及換檔時RPM的瞬時變化。")
    print("-----------------------------------------------------")
    for i in range(150): # 增加測試次數以便觀察更長時間的行為
        data = mock_obd_sensor.get_obd_data()
        # .model_dump() 是 pydantic v2 的標準方法，用來轉回字典以便列印
        print(f"數據點 {i+1}: Speed={data.speed:3} km/h, Gear={data.gear}, RPM={data.rpm:5}, Coolant={data.coolant_temp}°C, Battery={data.battery_voltage}V")
        time.sleep(0.3) # 縮短間隔以便更快觀察變化
