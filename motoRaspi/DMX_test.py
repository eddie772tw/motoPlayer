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
DEVICE_ADDRESS = "24:07:03:60:E0:68"  # 請替換成您截圖中的真實位址
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

async def main():
    logging.info(f"[*] 正在嘗試連接到 DMX 控制器: {DEVICE_ADDRESS}...")
    try:
        async with BleakClient(DEVICE_ADDRESS) as client:
            if not client.is_connected:
                logging.error("[!] 連接失敗。")
                return

            logging.info("[+] 連接成功！準備執行進階指令序列...")
            await asyncio.sleep(1)

            # --- 進階測試序列 ---

            # 1. 設定顏色為藍色
            cmd_blue = create_dmx_rgb_command(r=0, g=0, b=255)
            logging.info(f"[*] 1. 發送藍燈指令: {cmd_blue.hex()}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_blue, response=False)
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

            # 4. 切換到動態模式 1 (通常是七彩漸變之類的效果)
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

    except Exception as e:
        logging.error(f"[!] 發生錯誤: {e}")

if __name__ == "__main__":
    asyncio.run(main())
    logging.info("[*] 進階測試腳本執行完畢。")