# app/models.py

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class SystemStatus(BaseModel):
    """定義來自 NodeMCU 系統本身的狀態"""
    uno_status: Optional[str] = Field(None, alias="UNO")
    rfid_card: Optional[str] = Field(None, alias="card")

class EnvironmentalData(BaseModel):
    """定義來自環境感測器的數據"""
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    light_level: Optional[int] = Field(None, alias="light")

class OBDData(BaseModel):
    """
    (v4.0) 定義來自 OBD-II 的車輛數據。
    此版本已擴展以包含所有已知的可用感測器，並移除了檔位計算。
    """
    # --- 核心儀表板數據 (Core Dashboard Data) ---
    rpm: Optional[int] = Field(None, description="引擎轉速 (RPM)")
    speed: Optional[int] = Field(None, description="車輛時速 (km/h)")
    coolant_temp: Optional[float] = Field(None, description="引擎水溫 (°C)")
    battery_voltage: Optional[float] = Field(None, description="電瓶/控制模組電壓 (V)")

    # --- 性能分析數據 (Performance Tuning Data) ---
    throttle_pos: Optional[float] = Field(None, description="節氣門位置 (%)")
    engine_load: Optional[float] = Field(None, description="計算出的引擎負荷 (%)")
    abs_load_val: Optional[float] = Field(None, description="絕對負荷值 (%)")
    timing_advance: Optional[float] = Field(None, description="點火提前角 (°)")
    intake_air_temp: Optional[float] = Field(None, description="進氣溫度 (°C)")
    intake_map: Optional[int] = Field(None, description="進氣歧管絕對壓力 (kPa)")

    # --- 燃油系統數據 (Fuel System Data) ---
    fuel_system_status: Optional[str] = Field(None, description="燃油系統狀態")
    short_term_fuel_trim_b1: Optional[float] = Field(None, description="短期燃油修正 - Bank 1 (%)")
    long_term_fuel_trim_b1: Optional[float] = Field(None, description="長期燃油修正 - Bank 1 (%)")
    o2_sensor_voltage_b1s1: Optional[float] = Field(None, description="氧感測器電壓 - Bank 1 Sensor 1 (V)")


class MotoData(SystemStatus, EnvironmentalData, OBDData):
    """
    統一的 MotoPlayer 數據模型。
    """
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        populate_by_name = True
