# mock_obd.py (Synchronous Final)
#
# 版本: 6.0 (Sync Stable)
# 描述: 此版本已從非同步改回同步模式，以匹配新的 real_obd.py (RFCOMM版) 的介面。
#      這確保了開發者可以在真實與模擬 OBD 環境之間無縫切換。

import time
import random
from typing import Optional
import logging

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
        self.start_time = time.time()

    def connect(self) -> bool:
        """(同步) 模擬連線過程。"""
        logging.info("正在模擬連線到 OBD-II 適配器...")
        time.sleep(0.1)
        self.is_connected = True
        logging.info("模擬 OBD-II 適配器連線成功！")
        return True

    def disconnect(self):
        """(同步) 模擬中斷連線。"""
        self.is_connected = False
        logging.warning("[!]模擬 OBD-II 連線已關閉。")

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
        elif self.ride_state == 'ACCELERATING':
            self.speed += random.uniform(2, 8)
            self.rpm = self.speed * random.uniform(60, 90) + 1500
        elif self.ride_state == 'CRUISING':
            self.speed += random.uniform(-2, 2)
            self.rpm = self.speed * random.uniform(50, 70)
        elif self.ride_state == 'DECELERATING':
            self.speed = max(0, self.speed - random.uniform(5, 10))
            self.rpm = self.speed * random.uniform(40, 60) + 1500
        
        self.speed = max(0, min(self.speed, 200))
        self.rpm = max(0, min(self.rpm, 12000)) if self.speed > 0 else random.uniform(1400, 1600)
        
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
        )
