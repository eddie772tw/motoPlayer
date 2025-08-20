# OBD_test.py
#
# 版本: 2.5 (Car Scanner Logic)
# 目的: 根據 Car Scanner 的 BLE 側錄日誌，此版本恢復使用
#      "Notify" 作為主要通訊模式，並採用了更完整的初始化指令序列，
#      以最大限度地模擬成功通訊的條件。

import asyncio
import time
from bleak import BleakClient, BleakError
from typing import List, Tuple, Optional

# =================================================================
# ---               藍牙連線參數 (已確認)                       ---
# =================================================================
# ELM327 適配器的 MAC 位址
OBD_BLE_ADDRESS = "66:1E:32:8A:55:2C"

# 根據 Car Scanner 日誌確認的 UUIDs
UART_TX_CHAR_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"  # 用於寫入指令 (Write)
UART_RX_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"  # 用於接收通知 (Notify)

# =================================================================

# 全域變數，用於非同步通訊
response_queue = asyncio.Queue()
buffer = ""

def notification_handler(sender: int, data: bytearray):
    """(回呼函式) 處理從 BLE 特徵收到的通知數據。"""
    global buffer
    decoded_data = data.decode('utf-8', errors='ignore')
    # ELM327 的回應可能被分割成多個封包，我們需要將它們拼接起來
    buffer += decoded_data
    # ELM327 指令的標準結束符是 '>'
    if '>' in buffer:
        # 有時會收到多個回應，我們把它們分開處理
        responses = buffer.split('>')
        for res in responses[:-1]: # 最後一個元素可能是未完成的封包
            if res.strip():
                response_queue.put_nowait(res.strip() + '>')
        buffer = responses[-1] # 保留可能未完成的部分

async def send_and_wait(client: BleakClient, command: str, timeout: float = 5.0) -> str:
    """發送單一指令並等待其完整回應。"""
    global response_queue
    while not response_queue.empty():
        response_queue.get_nowait()

    await client.write_gatt_char(UART_TX_CHAR_UUID, (command + '\r').encode('utf-8'))
    
    try:
        # 等待 notification_handler 放入佇列的回應
        response = await asyncio.wait_for(response_queue.get(), timeout)
        return response.replace(command, "").replace(">", "").strip()
    except asyncio.TimeoutError:
        return "ERROR: TIMEOUT"

def interpret_response(response: str, command: str) -> Tuple[str, str]:
    """智慧分析 ELM327 的回應，判斷其真實狀態。"""
    if "ERROR: TIMEOUT" in response:
        return "通訊失敗", "在指定時間內未收到任何回應。"
    if "NO DATA" in response:
        return "ECU 無回應", "指令有效，但ECU未提供數據 (可能引擎未啟動或不支援此PID)。"
    if "?" in response:
        return "指令無效", f"ELM327 無法識別 '{command}' 指令。"
    if "ERROR" in response:
        return "匯流排錯誤", f"ELM327 在車輛通訊匯流排上偵測到錯誤: {response}"
    if not response.strip():
        return "空回應", "收到空的回應。"
    return "成功", response

async def run_test_case(client: BleakClient, description: str, command: str, iterations: int = 1):
    """執行單一測試案例並印出結果，包含性能計時與狀態分析。"""
    print(f"\n--- 測試案例: {description} ---")
    print(f"  指令: {command}")
    
    total_duration = 0
    successful_runs = 0

    for i in range(iterations):
        start_time = time.perf_counter()
        raw_response = await send_and_wait(client, command)
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        
        status, interpreted_msg = interpret_response(raw_response, command)
        
        if status == "成功":
            successful_runs += 1
            total_duration += duration_ms
        
        print(f"  第 {i+1}/{iterations} 次 -> 耗時: {duration_ms:6.1f} ms | 狀態: {status} | 詳細: {interpreted_msg}")
        
        await asyncio.sleep(0.1)

    if iterations > 1 and successful_runs > 0:
        avg_duration = total_duration / successful_runs
        print(f"  [結論] 平均耗時: {avg_duration:.1f} ms ({successful_runs}/{iterations} 次成功)")
    elif iterations > 1:
        print("  [結論] 所有運行均失敗或未收到有效數據。")


async def main():
    """主測試函式"""
    print("--- ELM327 BLE 自動化分析與測試工具 v2.5 ---")
    print(f"[*] 正在嘗試連線到: {OBD_BLE_ADDRESS}...")

    try:
        async with BleakClient(OBD_BLE_ADDRESS, transport="le") as client:
            if not client.is_connected:
                print("[!] 連線失敗。")
                return

            print(f"[+] 連線成功！")
            
            # --- 階段一: 啟用通知 (關鍵步驟) ---
            print(f"[*] 階段一: 啟用對 {UART_RX_CHAR_UUID} 的通知...")
            await client.start_notify(UART_RX_CHAR_UUID, notification_handler)
            print("[+] 通知已啟用。")
            print("-" * 50)

            # --- 階段二: 執行增強的初始化序列 ---
            print("[*] 階段二: 執行增強的初始化序列...")
            init_commands = ["ATZ", "ATE0", "ATL0", "ATH0", "ATSP0"]
            for cmd in init_commands:
                response = await send_and_wait(client, cmd)
                status, _ = interpret_response(response, cmd)
                print(f"  - 指令: {cmd:<5} | 狀態: {status:<12} | 回應: {response}")
                if status != "成功":
                    print("[!] 初始化失敗，測試中止。")
                    return
            print("[+] 初始化序列成功完成。")
            print("-" * 50)

            # --- 階段三: 自動化指令測試 ---
            print("\n[*] 階段三: 自動化執行指令測試...")
            
            await run_test_case(client, "查詢當前協議 (數字)", "ATDPN")
            await run_test_case(client, "查詢支援的 PID (01-20)", "0100")
            await run_test_case(client, "單一 PID 輪詢性能 (RPM)", "010C", iterations=10)
            await run_test_case(client, "多重 PID 輪詢性能 (RPM, Speed, Temp, Volt)", "01 0C 0D 05 42", iterations=10)

            print("\n--- 所有測試已完成 ---")

    except Exception as e:
        print(f"\n[!] 發生未預期的錯誤: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] 程式已由使用者中斷。")

