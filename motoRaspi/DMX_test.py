#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DMX_test.py

一個範例 Python 腳本，用於演示如何在 Raspberry Pi 上使用 bleak 函式庫
來控制一個透過 BLE (藍牙低功耗) 連接的 DMX RGB 燈條。

此腳本將執行以下操作：
1. 掃描附近的藍牙低功耗 (BLE) 裝置。
2. 嘗試連接到一個具有特定名稱的裝置 (例如 "DMX Light")。
3. 發現其服務和特徵。
4. 發送 DMX 指令到指定的特徵以執行測試序列：
   - 紅色 -> 綠色 -> 藍色 -> 關閉。
"""

import asyncio
import platform
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

# --- 設定 ---
# TODO: 請修改此處為您 DMX 裝置的實際名稱。
# 腳本將會尋找名稱包含此字串的裝置 (不區分大小寫)。
TARGET_DEVICE_NAME = "DMX"

# TODO: 如果您的裝置使用不同的 UUID，請在此修改。
# 這些是常用的預留位置。您可能需要使用 BLE 掃描器應用程式
# (例如手機上的 nRF Connect) 來找到您裝置正確的 UUID。
DMX_SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"  # 範例 DMX 服務 UUID
DMX_CHARACTERISTIC_UUID = "0000fff3-0000-1000-8000-00805f9b34fb" # 範例 DMX 特徵 UUID (用於寫入資料)

async def send_dmx_data(client: BleakClient, data: bytearray):
    """
    發送 DMX 資料封包到指定的特徵。

    參數:
        client: 已連接的 BleakClient 實例。
        data: 包含 DMX 通道資料的 bytearray。
    """
    try:
        print(f"正在發送 DMX 資料: {data.hex()}")
        # 'response=False' 通常用於 "Write Without Response" (無回應寫入) 的特徵，
        # 這在 DMX 控制中很常見，以實現更高的更新率。
        # 如果您的裝置需要寫入確認，請將其更改為 'response=True'。
        await client.write_gatt_char(DMX_CHARACTERISTIC_UUID, data, response=False)
    except BleakError as e:
        print(f"發送 DMX 資料時發生錯誤: {e}")
    except Exception as e:
        print(f"發送資料時發生未預期的錯誤: {e}")

async def main():
    """
    執行 BLE DMX 測試的主要非同步函式。
    """
    print("正在啟動 DMX BLE 測試腳本...")

    # 1. 掃描裝置
    print(f"正在掃描名稱為 '{TARGET_DEVICE_NAME}' 的裝置...")
    device = await BleakScanner.find_device_by_name(TARGET_DEVICE_NAME, timeout=10.0)

    if not device:
        print(f"--- 錯誤：找不到名稱為 '{TARGET_DEVICE_NAME}' 的裝置。 ---")
        print("請檢查以下事項：")
        print("1. DMX 燈條是否已通電並在訊號範圍內？")
        print("2. 腳本中的裝置名稱是否正確？")
        print("3. 此 Raspberry Pi 的藍牙功能是否已啟用？")
        return

    print(f"找到裝置: {device.name} ({device.address})")

    # 2. 連接到裝置
    async with BleakClient(device.address) as client:
        try:
            print(f"正在連接到 {device.name}...")
            if not await client.is_connected():
                print("--- 錯誤：連接失敗。 ---")
                return

            print(f"已成功連接到 {device.name}！")

            # 可選：驗證所需的服務/特徵是否存在
            # 這有助於在 UUID 不正確時進行除錯。
            service = client.services.get_service(DMX_SERVICE_UUID)
            if not service:
                print(f"--- 錯誤：找不到 DMX 服務 ({DMX_SERVICE_UUID})！ ---")
                print("可用的服務：")
                for s in client.services:
                    print(f"  - {s.uuid}")
                return

            characteristic = service.get_characteristic(DMX_CHARACTERISTIC_UUID)
            if not characteristic:
                print(f"--- 錯誤：找不到 DMX 特徵 ({DMX_CHARACTERISTIC_UUID})！ ---")
                return

            print("已找到 DMX 服務與特徵。正在開始測試序列...")
            await asyncio.sleep(1.0)

            # 3. 執行測試序列
            # 用於一個簡單的 3 通道 RGB 燈 (在通道 1, 2, 3) 的 DMX 封包
            # 格式: [通道 1 數值, 通道 2 數值, 通道 3 數值, ...]

            # 紅色
            print("\n--- 設定顏色為 紅色 ---")
            await send_dmx_data(client, bytearray([255, 0, 0]))
            await asyncio.sleep(2.0)

            # 綠色
            print("\n--- 設定顏色為 綠色 ---")
            await send_dmx_data(client, bytearray([0, 255, 0]))
            await asyncio.sleep(2.0)

            # 藍色
            print("\n--- 設定顏色為 藍色 ---")
            await send_dmx_data(client, bytearray([0, 0, 255]))
            await asyncio.sleep(2.0)

            # 白色 (全亮)
            print("\n--- 設定顏色為 白色 ---")
            await send_dmx_data(client, bytearray([255, 255, 255]))
            await asyncio.sleep(2.0)

            # 關閉
            print("\n--- 關閉燈光 ---")
            await send_dmx_data(client, bytearray([0, 0, 0]))
            await asyncio.sleep(1.0)

            print("\n測試序列完成。")

        except BleakError as e:
            print(f"--- 發生藍牙錯誤: {e} ---")
        except Exception as e:
            print(f"--- 發生未預期的錯誤: {e} ---")
        finally:
            if await client.is_connected():
                print("正在斷開與裝置的連接...")
                await client.disconnect()
            print("腳本執行完畢。")


if __name__ == "__main__":
    # 這個檢查對某些系統很重要。
    if platform.system() == "Linux":
        # 在 Linux 上，如果事件循環沒有被謹慎管理，bleak 有時會出現問題。
        # 使用 `asyncio.run()` 是標準做法。
        pass

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n使用者中斷腳本執行。")
    except Exception as e:
        print(f"主程式執行時發生未處理的錯誤: {e}")
