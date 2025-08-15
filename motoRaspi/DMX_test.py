# dmx_test.py
#
# 此版本直接鎖定目標 MAC 位址進行連接與測試，
# 用於對指定的 DMX 控制器進行最終的功能驗證。

import asyncio
import logging
from bleak import BleakClient, BleakError

# ----------------------------------------------------
#               參數
# ----------------------------------------------------
# 指定的 DMX 控制器 MAC 位址
DEVICE_ADDRESS = "24:07:03:60:E0:68" 

# 從 nRF Connect 偵察到的可寫入特徵 UUID
CHARACTERISTIC_UUID = "0000ae41-0000-1000-8000-00805f9b34fb"

# ----------------------------------------------------
#               私有協議指令產生器
# ----------------------------------------------------

def create_dmx_rgb_command(r: int, g: int, b: int, a: int = 255) -> bytearray:
    """
    根據協議文件，建構設定靜態顏色的 9 位元組指令。
    指令: [123, 255, 7, R, G, B, A, 255, 191]
    """
    return bytearray([123, 255, 7, r, g, b, a, 255, 191])

def create_dmx_power_command(is_on: bool) -> bytearray:
    """
    根據協議文件，建構開關指令。
    指令: [123, 255, 4, cmd, 255, 255, 255, 255, 191]
    """
    cmd = 1 if is_on else 0
    return bytearray([123, 255, 4, cmd, 255, 255, 255, 255, 191])

# ----------------------------------------------------

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def main():
    """
    主函式，執行連接並依序發送測試指令。
    """
    logging.info(f"[*] 準備直接連接到目標 DMX 控制器: {DEVICE_ADDRESS}...")
    
    try:
        async with BleakClient(DEVICE_ADDRESS) as client:
            if not client.is_connected:
                logging.error("[!] 連接失敗。請檢查設備是否在範圍內且已開機。")
                return

            logging.info("[+] 連接成功！準備執行指令序列...")
            await asyncio.sleep(1) # 連接後短暫等待，確保穩定

            # --- 測試序列 ---

            # 1. 亮藍燈 (Blue) - 作為清晰的視覺信號
            cmd_blue = create_dmx_rgb_command(r=0, g=0, b=255)
            logging.info(f"[*] 發送藍燈指令: {cmd_blue.hex()}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_blue, response=False)
            logging.info("[+] 藍燈指令已發送。")
            await asyncio.sleep(3)

            # 2. 關燈
            cmd_off = create_dmx_power_command(is_on=False)
            logging.info(f"[*] 發送關燈指令: {cmd_off.hex()}")
            await client.write_gatt_char(CHARACTERISTIC_UUID, cmd_off, response=False)
            logging.info("[+] 關燈指令已發送。")
            
            # --- 測試結束 ---

    except BleakError as e:
        logging.error(f"[!] 藍牙錯誤: {e}")
        logging.error("[!] 請確認 Python 腳本有足夠的權限執行藍牙操作 (例如使用 sudo)。")
    except Exception as e:
        logging.error(f"[!] 發生未知錯誤: {e}")

if __name__ == "__main__":
    asyncio.run(main())
    logging.info("[*] 測試腳本執行完畢。")