# Copyright (C) 2026 eddie772tw
# This file is part of motoPlayer.
# motoPlayer is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# motoRaspi/DMX.py
import asyncio
import logging
from bleak import BleakClient, BleakError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')

class DMXController:
    """
    一個非同步的 DMX BLE 控制器類別，封裝了所有通訊協議。
    """
    def __init__(self, device_address: str):
        self._device_address = device_address
        self._characteristic_uuid = "0000ffe1-0000-1000-8000-00805f9b34fb"
        self._client = BleakClient(self._device_address, timeout=10.0)
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    async def connect(self):
        """明確地連接到設備。"""
        if not self.is_connected:
            logger.info(f"正在連接到 DMX 控制器: {self._device_address}")
            await self._client.connect()

    async def disconnect(self):
        """明確地中斷與設備的連接。"""
        if self.is_connected:
            logger.info("正在中斷與 DMX 控制器的連接...")
            await self._client.disconnect()

    async def _send_command(self, command: bytearray):
        """一個統一的、帶有鎖和自動重連機制的指令發送函式。"""
        async with self._lock:
            try:
                if not self.is_connected:
                    await self.connect()
                
                logger.debug(f"發送指令: {command.hex()}")
                await self._client.write_gatt_char(self._characteristic_uuid, command, response=False)
            except BleakError as e:
                logger.error(f"藍牙錯誤: {e}")
                raise
            except Exception as e:
                logger.error(f"發送指令時發生未知錯誤: {e}")
                raise

    # --- 功能性 API ---

    async def set_static_color(self, r: int, g: int, b: int, a: int = 255):
        """設定靜態顏色"""
        command = bytearray([123, 255, 7, r, g, b, a, 255, 191])
        await self._send_command(command)

    async def set_power(self, is_on: bool):
        """設定電源開關"""
        cmd = 1 if is_on else 0
        command = bytearray([123, 255, 4, cmd, 255, 255, 255, 255, 191])
        await self._send_command(command)

    async def set_brightness(self, brightness: int):
        """設定亮度 (0-100)"""
        bri = max(0, min(100, brightness))
        bri_scaled = (bri * 32) // 100
        command = bytearray([123, 255, 1, bri_scaled, bri, 1, 255, 255, 191])
        await self._send_command(command)
    
    async def set_mode(self, mode: int):
        """設定動態模式 (1-255)"""
        command = bytearray([123, 255, 3, mode, 255, 255, 255, 255, 191])
        await self._send_command(command)
        
    async def set_speed(self, speed: int):
        """設定動態模式的速度 (0-100)"""
        spd = max(0, min(100, speed))
        command = bytearray([123, 255, 2, spd, 255, 1, 255, 255, 191])
        await self._send_command(command)
