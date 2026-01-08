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

# --- 基礎轉換函式 ---
# 這些函式負責將 ECU 回傳的 HEX 值陣列轉換為有意義的物理單位。

def _convert_rpm(hex_bytes: list) -> Optional[int]:
    """計算引擎轉速 (RPM)"""
    try:
        a = int(hex_bytes[0], 16)
        b = int(hex_bytes[1], 16)
        return int(((a * 256) + b) / 4)
    except (ValueError, IndexError):
        return None

def _convert_speed(hex_bytes: list) -> Optional[int]:
    """計算車輛速度 (km/h)"""
    try:
        return int(hex_bytes[0], 16)
    except (ValueError, IndexError):
        return None

def _convert_temp(hex_bytes: list) -> Optional[float]:
    """計算溫度 (°C)"""
    try:
        return float(int(hex_bytes[0], 16) - 40)
    except (ValueError, IndexError):
        return None

def _convert_percent(hex_bytes: list) -> Optional[float]:
    """計算百分比 (公式: A * 100 / 255)"""
    try:
        return round((int(hex_bytes[0], 16) * 100) / 255.0, 2)
    except (ValueError, IndexError):
        return None

def _convert_fuel_trim_percent(hex_bytes: list) -> Optional[float]:
    """計算燃油修正百分比 (公式: (A - 128) * 100 / 128)"""
    try:
        return round(((int(hex_bytes[0], 16) - 128) * 100) / 128.0, 2)
    except (ValueError, IndexError):
        return None
        
def _convert_intake_pressure(hex_bytes: list) -> Optional[int]:
    """計算進氣歧管絕對壓力 (kPa)"""
    try:
        return int(hex_bytes[0], 16)
    except (ValueError, IndexError):
        return None

def _convert_timing_advance(hex_bytes: list) -> Optional[float]:
    """計算點火正時提前角 (相對於上死點)"""
    try:
        return round((int(hex_bytes[0], 16) - 128) / 2.0, 1)
    except (ValueError, IndexError):
        return None

def _convert_maf(hex_bytes: list) -> Optional[float]:
    """計算空氣流量 (g/s)"""
    try:
        a = int(hex_bytes[0], 16)
        b = int(hex_bytes[1], 16)
        return round(((a * 256) + b) / 100.0, 2)
    except (ValueError, IndexError):
        return None

def _convert_run_time(hex_bytes: list) -> Optional[int]:
    """計算引擎啟動後運轉時間 (秒)"""
    try:
        a = int(hex_bytes[0], 16)
        b = int(hex_bytes[1], 16)
        return (a * 256) + b
    except (ValueError, IndexError):
        return None

# --- PID 與轉換公式的對應字典 ---
# Key: PID 指令 (不含 '01' 模式)
# Value: 對應的轉換函式
PID_FORMULAS: Dict[str, Callable[[list], Any]] = {
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

def decode_pid_response(pid: str, response: str) -> Optional[Any]:
    """
    解碼單一 PID 的 ELM37 回應。

    Args:
        pid (str): 發送的 PID 指令 (例如 "010C")。
        response (str): 從 ELM327 收到的原始回應字串。

    Returns:
        轉換後的數值，如果解碼失敗或不支援則回傳 None。
    """
    if not pid or not response:
        return None
        
    pid_code = pid[2:]
    
    if pid_code not in PID_FORMULAS:
        # 對於沒有定義公式的 PID，直接回傳原始值或 None
        return response

    parts = response.split()
    
    # 驗證回應格式是否正確 (例如 "41 0C 1A F8")
    if len(parts) < 3 or parts[0] != "41" or parts[1].upper() != pid_code.upper():
        return None

    hex_data_bytes = parts[2:]
    
    conversion_function = PID_FORMULAS[pid_code]
    return conversion_function(hex_data_bytes)

