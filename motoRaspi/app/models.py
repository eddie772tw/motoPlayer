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
    """定義來自 OBD-II 的車輛數據"""
    rpm: Optional[int] = None
    speed: Optional[int] = None
    coolant_temp: Optional[float] = None
    battery_voltage: Optional[float] = None
    gear: Optional[int] = None

class MotoData(SystemStatus, EnvironmentalData, OBDData):
    """
    統一的 MotoPlayer 數據模型。
    這個類別整合了所有來源的數據，作為我們系統中數據交換的標準格式。
    """
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        # Pydantic 的設定，允許我們使用別名 (例如將 JSON 中的 "UNO" 對應到 uno_status)
        populate_by_name = True