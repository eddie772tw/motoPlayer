# Copyright (C) 2026 eddie772tw
# This file is part of motoPlayer.
# motoPlayer is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# mock_obd.py (Synchronous Final)
#
# 版本: 6.5 (Clean Logging)
# 描述: 此版本已從非同步改回同步模式。
#      擴充了數據模擬的範圍。
#      [NEW] 將所有 print() 語句替換為標準的 logging 模組，
#      並移除了日誌中的標籤，以匹配 real_obd.py 的風格。

import time
import random
import logging
from typing import Optional

try:
    from app.models import OBDData
except ImportError:
    logging.warning("無法匯入 'app.models'。將使用內部模擬的 OBDData 類別。")
    class OBDData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def __repr__(self): return f"OBDData({self.__dict__})"

class MockOBD:
    """
    一個數據驅動的、同步的 OBD-II 模擬器。
    """
    def __init__(self):
        self.ride_state = 'IDLE'
        self.state_timer = time.time()
        self.is_connected = False
        self.rpm = 1500
        self.speed = 0
        self.coolant_temp = 45.0
        self.battery_voltage = 12.6
        self.throttle_pos = 3.0
        self.engine_load = 15.0
        self.start_time = time.time()

    def connect(self) -> bool:
        logging.info("正在模擬連線到 OBD-II 適配器...")
        time.sleep(0.1)
        self.is_connected = True
        logging.info("模擬 OBD-II 適配器連線成功！")
        return True

    def disconnect(self):
        self.is_connected = False
        logging.info("模擬 OBD-II 連線已關閉。")

    def _update_ride_state(self):
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
        self._update_ride_state()
        
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

        self.speed = max(0, min(self.speed, 200))
        self.rpm = max(0, min(self.rpm, 12000)) if self.speed > 0 else random.uniform(1400, 1600)
        self.throttle_pos = max(0, min(self.throttle_pos, 100))
        self.engine_load = max(0, min(self.engine_load, 100))
        
        elapsed_time = time.time() - self.start_time
        if self.coolant_temp < 90:
            self.coolant_temp += elapsed_time * 0.01
        else:
            self.coolant_temp = random.uniform(88.0, 95.0)
        
        self.battery_voltage = random.uniform(13.8, 14.4) if self.rpm > 1000 else 12.6

    def get_obd_data(self) -> OBDData:
        """(同步) 獲取一組模擬的 OBD-II 數據。"""
        if not self.is_connected:
            return OBDData()
        
        self._generate_data_based_on_state()

        return OBDData(
            rpm=int(self.rpm),
            speed=int(self.speed),
            coolant_temp=round(self.coolant_temp, 1),
            battery_voltage=round(self.battery_voltage, 2),
            engine_load=round(self.engine_load, 2),
            throttle_pos=round(self.throttle_pos, 2),
        )

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
    
    logging.info("--- MockOBD (Sync) 獨立測試模式 ---")
    mock_sensor = MockOBD()
    try:
        if mock_sensor.connect():
            logging.info("--- 開始循環生成數據 (每秒一次)，按 Ctrl+C 結束 ---")
            while True:
                data = mock_sensor.get_obd_data()
                log_message = (
                    f"State: {mock_sensor.ride_state.ljust(12)} | "
                    f"RPM: {data.rpm}, Speed: {data.speed}, "
                    f"Temp: {data.coolant_temp}, Volt: {data.battery_voltage}, "
                    f"Load: {data.engine_load}%, Throttle: {data.throttle_pos}%"
                )
                logging.info(log_message)
                time.sleep(1.0)
    except KeyboardInterrupt:
        logging.info("使用者手動中斷程式。")
    finally:
        mock_sensor.disconnect()
