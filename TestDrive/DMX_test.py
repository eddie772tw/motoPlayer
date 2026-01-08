# Copyright (C) 2026 eddie772tw
# This file is part of motoPlayer.
# motoPlayer is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# dmx_test.py (版本 4 - 多功能測試)
#
# 整合了亮度、模式、速度等多項控制指令，
# 用於全面驗證 DMX 控制器的功能。

import asyncio
import logging
from bleak import BleakClient, BleakError

# ----------------------------------------------------
#               參數 (請確認與您的設備相符)
# ----------------------------------------------------
DEVICE_ADDRESS = [
    "24:07:03:60:E0:68",
    "24:07:03:50:B1:20"
]
# DEVICE_ADDRESS = "24:07:03:60:E0:68"  # 請替換成您截圖中的真實位址
CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# ----------------------------------------------------
#               私有協議指令產生器 (已擴充)
# ----------------------------------------------------

def create_dmx_rgb_command(r: int, g: int, b: int, a: int = 255) -> bytearray:
    """指令碼 7: 設定靜態顏色"""
    return bytearray([123, 255, 7, r, g, b, a, 255, 191])

def create_dmx_power_command(is_on: bool) -> bytearray:
    """指令碼 4: 開/關"""
    cmd = 1 if is_on else 0
    return bytearray([123, 255, 4, cmd, 255, 255, 255, 255, 191])

def create_dmx_brightness_command(brightness: int) -> bytearray:
    """
    指令碼 1: 設定亮度 (0-100)
    協議文件顯示亮度參數需要兩個值: bri (0-100) 和 bri_scaled ((bri * 32) / 100)
    """
    if not 0 <= brightness <= 100:
        raise ValueError("亮度必須在 0 到 100 之間")
    bri = brightness
    bri_scaled = (bri * 32) // 100
    on_off = 1 if bri > 0 else 0
    return bytearray([123, 255, 1, bri_scaled, bri, on_off, 255, 255, 191])

def create_dmx_mode_command(mode: int) -> bytearray:
    """指令碼 3: 設定動態模式"""
    return bytearray([123, 255, 3, mode, 255, 255, 255, 255, 191])

def create_dmx_speed_command(speed: int) -> bytearray:
    """指令碼 2: 設定模式速度 (0-100)"""
    if not 0 <= speed <= 100:
        raise ValueError("速度必須在 0 到 100 之間")
    return bytearray([123, 255, 2, speed, 255, 1, 255, 255, 191]) # direction 暫定為 1

# ----------------------------------------------------

logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')

async def test_device(address: str):
    """
    連接到指定的 DMX 控制器並執行完整的測試序列。
    """
    logging.info(f"[*] 正在嘗試連接到 DMX 控制器: {address}...")
    try:
        # 增加 timeout 參數以避免長時間等待無響應的設備
        async with BleakClient(address, timeout=10.0) as client:
            if not client.is_connected:
                # 這個判斷理論上在 `async with` 成功後不會觸發，但作為雙重保險
                logging.error(f"[!] 連接至 {address} 失敗。")
                return

            logging.info(f"[+] 成功連接到 {address}！準備執行指令序列...")
            await asyncio.sleep(1)

            # --- 測試序列 ---

            # 1. 設定顏色為 #7f4448
            cmd_color = create_dmx_rgb_command(r=127, g=68, b=72)
            logging.info(f"[*] 1. 發送顏色指令 ({cmd_color.hex()})")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_color, response=False)
            await asyncio.sleep(2)

            # 2. 將亮度調暗至 20%
            cmd_bright_low = create_dmx_brightness_command(brightness=20)
            logging.info(f"[*] 2. 發送低亮度 (20%) 指令: {cmd_bright_low.hex()}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_bright_low, response=False)
            await asyncio.sleep(2)

            # 3. 將亮度調回 100%
            cmd_bright_high = create_dmx_brightness_command(brightness=100)
            logging.info(f"[*] 3. 發送高亮度 (100%) 指令: {cmd_bright_high.hex()}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_bright_high, response=False)
            await asyncio.sleep(2)

            # 4. 切換到動態模式 1 (七彩漸變)
            cmd_mode_1 = create_dmx_mode_command(mode=1)
            logging.info(f"[*] 4. 切換到動態模式 1: {cmd_mode_1.hex()}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_mode_1, response=False)
            await asyncio.sleep(2)

            # 5. 將模式速度設定為 80%
            cmd_speed = create_dmx_speed_command(speed=80)
            logging.info(f"[*] 5. 設定模式速度 (80%): {cmd_speed.hex()}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_speed, response=False)
            logging.info("[*] 請觀察燈光動態效果的速度變化...")
            await asyncio.sleep(4)

            # 6. 關燈
            cmd_off = create_dmx_power_command(is_on=False)
            logging.info(f"[*] 6. 發送關燈指令: {cmd_off.hex()}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_off, response=False)
            await asyncio.sleep(1) # 確保指令有足夠時間發送

            logging.info(f"[+] {address} 的測試序列執行完畢。")

    except BleakError as e:
        logging.error(f"[!] 連接至 {address} 時發生 Bleak 錯誤: {e}")
    except Exception as e:
        # 捕捉其他潛在錯誤，例如指令產生或異步操作中的問題
        logging.error(f"[!] 處理 {address} 時發生未預期錯誤: {e}")


async def main():
    """
    創建所有設備的測試任務並發執行它們。
    """
    logging.info("[*] 開始執行 DMX 控制器多設備並發測試...")
    # 為每個設備地址創建一個測試任務
    tasks = [test_device(address) for address in DEVICE_ADDRESS]
    # 使用 asyncio.gather 來並發執行所有任務
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("\n[*] 測試被使用者中斷。")
    finally:
        logging.info("[*] 所有設備的並發測試流程已結束。")