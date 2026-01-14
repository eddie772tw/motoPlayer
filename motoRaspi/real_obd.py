# Copyright (C) 2026 eddie772tw
# This file is part of motoPlayer.
# motoPlayer is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# real_obd.py (RFCOMM Final)
#
# 版本: 6.8 (Standardized Logging)
# 描述: [MODIFIED] 將日誌格式統一為 '[%(levelname)s][%(asctime)s]%(message)s'。

import bluetooth
import time
import logging
from typing import Optional

from obd_converter import decode_pid_response, parse_fast_response

try:
    from app.models import OBDData
except ImportError:
    logging.warning("無法匯入 'app.models'。將使用內部模擬的 OBDData 類別。")
    class OBDData:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def __repr__(self): return f"OBDData({self.__dict__})"

# =================================================================
# ---               ELM327 指令集 (Constants)                   ---
# =================================================================

ELM327_BASE_INIT = [
    "ATZ",
    "ATE0",
    "ATL0",
    "ATH0",
    "ATS0",
    "ATAT1",
]

PIDS_TO_QUERY = {
    "rpm": "010C",
    "speed": "010D",
    "coolant_temp": "0105",
    "engine_load": "0104",
    "throttle_pos": "0111",
    "battery_voltage": "ATRV",
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
            self.sock.settimeout(2.0)
            logging.info("RFCOMM Socket 連線成功！")

            logging.info("正在執行基礎 ELM327 初始化...")
            for cmd in ELM327_BASE_INIT:
                response = self._send_command(cmd)
                logging.info(f"  > {cmd:<5}... {response.splitlines()[0]}")
                if "OK" not in response and "ELM" not in response:
                    logging.error(f"基礎初始化指令 '{cmd}' 失敗，中止連線。")
                    self.disconnect()
                    return False
                time.sleep(0.1)
            
            logging.info("正在嘗試與 ECU 建立通訊...")

            logging.info("第一步：嘗試使用指定的協議 (ATSP5)...")
            self._send_command("ATSP5")
            response = self._send_command("0100")

            if "NO DATA" not in response and "ERROR" not in response:
                logging.info("協議 ATSP5 連線成功！")
            else:
                logging.warning("使用 ATSP5 與 ECU 通訊失敗，正在回退到自動協議 (ATSP0)...")
                self._send_command("ATSP0")
                response = self._send_command("0100")

                if "NO DATA" in response or "ERROR" in response:
                    logging.error(f"使用自動協議 ATSP0 仍然無法與 ECU 建立通訊: {response.splitlines()[0]}")
                    self.disconnect()
                    return False
                logging.info("協議 ATSP0 連線成功！")

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
        """發送指令並回傳 String (舊容相容)"""
        raw = self._send_command_bytes(command)
        return raw.decode('utf-8', errors='ignore').strip()

    def _send_command_bytes(self, command: str) -> bytes:
        """發送指令並回傳 Raw Bytes"""
        if not self.sock:
            return b"ERROR"
        
        # Flush input buffer
        self.sock.setblocking(False)
        try:
            while True:
                r = self.sock.recv(1024)
                if not r: break
        except bluetooth.btcommon.BluetoothError:
            pass
        self.sock.setblocking(True)

        self.sock.send((command + '\r').encode('utf-8'))
        
        buffer = b""
        while True:
            try:
                data = self.sock.recv(1024)
                if not data:
                    break
                buffer += data
                # 檢查結尾符號 '>'
                if b'>' in buffer:
                    break
            except bluetooth.btcommon.BluetoothError as e:
                if "timed out" in str(e):
                    logging.warning("OBD Command Timeout")
                    return b"TIMEOUT"
                raise e
        return buffer

    def _parse_voltage(self, response: bytes) -> Optional[float]:
        try:
            # ATRV response: b'12.4V'
            s = response.decode('utf-8', errors='ignore').replace("V", "").strip()
            return float(s)
        except:
            return None

    def get_fast_data(self) -> OBDData:
        """
        使用優化後的批次讀取模式。
        一次發送 0104050C0D11 (Load, Coolant, RPM, Speed, Throttle)
        """
        if not self.is_connected:
            return OBDData()

        # 1. 批次讀取主要行車數據
        # 04:Load, 05:Temp, 0C:RPM, 0D:Speed, 11:Throttle
        raw_response = self._send_command_bytes("0104050C0D11")
        parsed = parse_fast_response(raw_response)

        # 2. 獨立讀取電壓 (非標準 PID)
        volt_resp = self._send_command_bytes("ATRV")
        voltage = self._parse_voltage(volt_resp)

        # 3. 組裝 OBDData
        return OBDData(
            rpm=parsed.get("0C"),
            speed=parsed.get("0D"),
            coolant_temp=parsed.get("05"),
            engine_load=parsed.get("04"),
            throttle_pos=parsed.get("11"),
            battery_voltage=voltage
        )

    def get_obd_data(self) -> OBDData:
        # 將默認行為切換為 Fast Data 模式
        return self.get_fast_data()

if __name__ == '__main__':
    # [MODIFIED] 更新日誌格式
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
                
                log_message = (
                    f"Time:{duration_ms:6.1f}ms | "
                    f"RPM:{data.rpm or 'N/A'} | "
                    f"Speed:{data.speed or 'N/A'} | "
                    f"Temp:{data.coolant_temp or 'N/A'} | "
                    f"Volt:{data.battery_voltage or 'N/A'} | "
                    f"Load:{data.engine_load or 'N/A'}% | "
                    f"Throttle:{data.throttle_pos or 'N/A'}%"
                )
                
                if duration_ms > 200:
                    logging.warning(f"SLOW POLLING! {log_message}")
                else:
                    logging.info(log_message)
                
                time.sleep(1.0)

    except KeyboardInterrupt:
        logging.info("使用者手動中斷程式。")
    except Exception as e:
        logging.error(f"測試過程中發生未預期的錯誤: {e}")
    finally:
        logging.info("正在關閉連線...")
        obd_sensor.disconnect()
