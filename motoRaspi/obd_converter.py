# Copyright (C) 2026 eddie772tw
# This file is part of motoPlayer.
# motoPlayer is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# obd_converter.py
#
# 版本: 2.0 (Expanded)
# 目的: 提供一個中心化的 OBD-II 數據轉換與解析模組。
#      此版本已根據參考資料擴充，包含了更完整的 PID 解碼公式。

from typing import Optional, Callable, Dict, Any

# --- PID config ---
# 定義每個 PID 的回傳數據字節數 (不含 PID 本身)
# 用於從連續的 HEX 字串中切割數據
PID_DATA_BYTES = {
    "04": 1,  # Engine Load
    "05": 1,  # Coolant Temp
    "06": 1,  # Short Term Fuel Trim
    "07": 1,  # Long Term Fuel Trim
    "0B": 1,  # MAP
    "0C": 2,  # RPM
    "0D": 1,  # Speed
    "0E": 1,  # Timing Advance
    "0F": 1,  # Intake Temp
    "10": 2,  # MAF
    "11": 1,  # Throttle Pos
    "1F": 2,  # Run Time
    "4D": 2,  # Time with MIL
}

# --- 基礎轉換函式 (Byte-level optimization) ---
# 接收 ASCII Hex bytes (例如 b'1A' 或 b'1AF8') 直接轉數值。
# 注意: 輸入的是 ASCII 編碼的十六進制字串 (bytes 類型)，例如 b'1A'。
# int(val_bytes, 16) 會將其轉換為整數數值 (即 A 或 A*256+B)。

def _convert_rpm(val_bytes: bytes) -> Optional[int]:
    """
    計算引擎轉速 (RPM)。
    原始公式: ((A * 256) + B) / 4
    優化邏輯: A*256+B 即為輸入的 2 byte 數值 (val)。
             除以 4 等同於位元右移 2 位 (>> 2)。
    """
    try:
        # Optimization: division by 4 is equivalent to right shift by 2
        return int(val_bytes, 16) >> 2
    except ValueError:
        return None

def _convert_speed(val_bytes: bytes) -> Optional[int]:
    """
    計算車輛速度 (km/h)。
    原始公式: A
    說明: 直接回傳該字節的數值。
    """
    try:
        return int(val_bytes, 16)
    except ValueError:
        return None

def _convert_temp(val_bytes: bytes) -> Optional[float]:
    """
    計算溫度 (°C)。
    原始公式: A - 40
    說明: 範圍從 -40°C 到 215°C。
    """
    try:
        return float(int(val_bytes, 16) - 40)
    except ValueError:
        return None

def _convert_percent(val_bytes: bytes) -> Optional[float]:
    """
    計算百分比 (%)，用於負荷、節氣門等。
    原始公式: A * 100 / 255
    說明: 將 0-255 的數值映射到 0-100%。
    """
    try:
        return round((int(val_bytes, 16) * 100) / 255.0, 2)
    except ValueError:
        return None

def _convert_fuel_trim_percent(val_bytes: bytes) -> Optional[float]:
    """
    計算燃油修正百分比 (%)。
    原始公式: (A - 128) * 100 / 128
    說明: 128 為 0%，小於 128 為削減，大於 128 為增加。
    """
    try:
        return round(((int(val_bytes, 16) - 128) * 100) / 128.0, 2)
    except ValueError:
        return None
        
def _convert_intake_pressure(val_bytes: bytes) -> Optional[int]:
    """
    計算進氣歧管絕對壓力 (kPa)。
    原始公式: A
    說明: 直接回傳壓力值 (kPa)。
    """
    try:
        return int(val_bytes, 16)
    except ValueError:
        return None

def _convert_timing_advance(val_bytes: bytes) -> Optional[float]:
    """
    計算點火正時提前角 (度)。
    原始公式: (A - 128) / 2
    說明: 相對於上死點 (TDC) 的角度。
    """
    try:
        return round((int(val_bytes, 16) - 128) / 2.0, 1)
    except ValueError:
        return None

def _convert_maf(val_bytes: bytes) -> Optional[float]:
    """
    計算空氣流量 (g/s)。
    原始公式: ((A * 256) + B) / 100
    說明: 將 2 byte 數值除以 100。
    """
    try:
        return round(int(val_bytes, 16) / 100.0, 2)
    except ValueError:
        return None

def _convert_run_time(val_bytes: bytes) -> Optional[int]:
    """
    計算運轉時間 (秒)。
    原始公式: (A * 256) + B
    說明: 直接回傳總秒數。
    """
    try:
        return int(val_bytes, 16)
    except ValueError:
        return None

# --- PID 與轉換公式的對應字典 ---
PID_FORMULAS: Dict[str, Callable[[bytes], Any]] = {
    "04": _convert_percent,             # 計算後的引擎負荷 (Calculated Engine Load)
    "05": _convert_temp,                # 引擎冷卻液溫度 (Engine Coolant Temperature)
    "06": _convert_fuel_trim_percent,   # 短期燃油修正 - Bank 1 (Short Term Fuel Trim—Bank 1)
    "07": _convert_fuel_trim_percent,   # 長期燃油修正 - Bank 1 (Long Term Fuel Trim—Bank 1)
    "0B": _convert_intake_pressure,     # 進氣歧管絕對壓力 (Intake Manifold Absolute Pressure)
    "0C": _convert_rpm,                 # 引擎轉速 (RPM)
    "0D": _convert_speed,               # 車輛速度 (Speed)
    "0E": _convert_timing_advance,      # 1號汽缸點火正時提前角 (Timing Advance)
    "0F": _convert_temp,                # 進氣溫度 (Intake Air Temperature)
    "10": _convert_maf,                 # 空氣流量計氣流速率 (MAF Air Flow Rate)
    "11": _convert_percent,             # 節氣門位置 (Throttle Position)
    "1F": _convert_run_time,            # 引擎啟動後運轉時間 (Run time since engine start)
    "4D": _convert_run_time,            # 引擎故障燈(MIL)亮起後的運轉時間 (Time run with MIL on)
}

def decode_pid_response(pid: str, response: Any) -> Optional[Any]:
    """
    解碼單一 PID 的 ELM37 回應 (支援 str 或 bytes)。
    相容 ATS0 (無空白) 模式。
    """
    if not pid or not response:
        return None
    
    # 標準化輸入為 bytes
    if isinstance(response, str):
        response_bytes = response.encode('ascii', errors='ignore')
    else:
        response_bytes = response
        
    pid_code = pid[2:]
    if pid_code not in PID_FORMULAS:
        return response

    # 簡單驗證 header (41 + PID)
    # 預期格式: b'410C...' (No spaces) or b'41 0C ...' (Spaces)
    # 我們先嘗試移除所有空白 (bytes replace)
    clean_resp = response_bytes.replace(b' ', b'').replace(b'\r', b'').replace(b'\n', b'')
    
    expected_header = b'41' + pid_code.encode('ascii')
    
    if not clean_resp.startswith(expected_header):
        return None

    # 取得數據部分
    data_part = clean_resp[len(expected_header):]
    
    # 呼叫轉換函式
    func = PID_FORMULAS[pid_code]
    return func(data_part)

def parse_fast_response(response: bytes) -> Dict[str, Any]:
    """
    解析來自 get_fast_data 的組合回應 (raw bytes from ATS0 mode)。
    預期格式: 41 + PID1 + DATA1 + PID2 + DATA2 ...
    例如: b'410C1AF80D32...'
    """
    results = {}
    
    # 清理非 hex 字符 (除了 \r\n 可能已經在上層處理過，這裡再保險一次)
    clean_resp = response.replace(b' ', b'').replace(b'\r', b'').replace(b'\n', b'').replace(b'>', b'')

    # 必須以 41 開頭
    if not clean_resp.startswith(b'41'):
        return results

    # 從 41 之後開始解析
    cursor = 2 # Skip '41'
    total_len = len(clean_resp)

    while cursor < total_len:
        # 讀取 2 chars 作為 PID
        if cursor + 2 > total_len:
            break
            
        pid_hex = clean_resp[cursor : cursor+2].decode('ascii')
        cursor += 2
        
        # 查表得知數據長度
        data_bytes_count = PID_DATA_BYTES.get(pid_hex)
        if data_bytes_count is None:
            # 未知 PID，無法繼續解析後續字串，因為不知道長度
            # Log warning? For performance we just stop or break.
            break
            
        # ASCII hex chars length = bytes * 2
        ascii_len = data_bytes_count * 2
        
        if cursor + ascii_len > total_len:
            # 數據不完整
            break
            
        val_ascii_bytes = clean_resp[cursor : cursor + ascii_len]
        cursor += ascii_len
        
        # 轉換
        func = PID_FORMULAS.get(pid_hex)
        if func:
            # Mapping PID to readable key names (Optional, needed for RealOBD struct)
            # 這裡我們只回傳 PID:Value 的 dict，由 RealOBD 組裝
            results[pid_hex] = func(val_ascii_bytes)
            
    return results

