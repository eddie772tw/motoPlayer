# OBD_test.py
#
# 版本: 2.3 (Intelligent Response Analysis)
# 目的: 一個自動化的 BLE OBD-II 分析與測試工具。
#      它會自動探索、測試，並能智慧分析 ELM327 的回應，
#      以區分是通訊失敗、指令錯誤，還是 ECU 的正常無回應。

import asyncio
import time
from bleak import BleakClient, BleakError
from typing import List, Tuple, Optional

# =================================================================
# ---               藍牙連線參數 (建議的預設值)                 ---
# =================================================================
# ELM327 適配器的 MAC 位址
OBD_BLE_ADDRESS = "66:1E:32:8A:55:2C"

# 我們推測的 UART 服務與特徵 UUIDs (作為首次嘗試的目標)。
DEFAULT_UART_TX_CHAR_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"
DEFAULT_UART_RX_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

# =================================================================

# 全域變數，用於非同步通訊
response_queue = asyncio.Queue()
buffer = ""

def notification_handler(sender: int, data: bytearray):
    """(回呼函式) 處理從 BLE 特徵收到的通知數據。"""
    global buffer
    decoded_data = data.decode('utf-8', errors='ignore')
    buffer += decoded_data
    if '>' in buffer:
        response_queue.put_nowait(buffer.strip())
        buffer = ""

async def send_and_wait(client: BleakClient, tx_uuid: str, command: str, timeout: float = 5.0) -> str:
    """發送單一指令並等待其完整回應。"""
    global response_queue
    while not response_queue.empty():
        response_queue.get_nowait()

    await client.write_gatt_char(tx_uuid, (command + '\r').encode('utf-8'))
    
    try:
        response = await asyncio.wait_for(response_queue.get(), timeout)
        return response.replace(command, "").replace(">", "").strip()
    except asyncio.TimeoutError:
        return "ERROR: TIMEOUT"

def interpret_response(response: str, command: str) -> Tuple[str, str]:
    """
    [NEW] 智慧分析 ELM327 的回應，判斷其真實狀態。
    """
    if "ERROR: TIMEOUT" in response:
        return "通訊失敗", "在指定時間內未收到任何回應。"
    if "NO DATA" in response:
        return "ECU 無回應", "指令有效，但ECU未提供數據 (可能引擎未啟動或不支援此PID)。"
    if "?" in response:
        return "指令無效", f"ELM327 無法識別 '{command}' 指令。"
    if "ERROR" in response:
        return "匯流排錯誤", f"ELM327 在車輛通訊匯流排上偵測到錯誤: {response}"
    if not response.strip():
        return "空回應", "收到空的回應，可能協議不匹配。"
    return "成功", response


async def run_test_case(client: BleakClient, tx_uuid: str, description: str, command: str, iterations: int = 1):
    """執行單一測試案例並印出結果，包含性能計時與狀態分析。"""
    print(f"\n--- 測試案例: {description} ---")
    print(f"  指令: {command}")
    
    total_duration = 0
    successful_runs = 0

    for i in range(iterations):
        start_time = time.perf_counter()
        raw_response = await send_and_wait(client, tx_uuid, command)
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
    print("--- ELM327 BLE 自動化分析與測試工具 v2.3 ---")
    print(f"[*] 正在嘗試連線到: {OBD_BLE_ADDRESS}...")

    try:
        async with BleakClient(OBD_BLE_ADDRESS) as client:
            if not client.is_connected:
                print("[!] 連線失敗。")
                return

            print(f"[+] 連線成功！設備名稱: {client.address}")
            print("-" * 50)

            # --- 階段一: 自動探索服務與特徵 ---
            print("[*] 階段一: 自動探索設備上的服務與特徵...")
            candidate_pairs: List[Tuple[str, str]] = []
            candidate_pairs.append((DEFAULT_UART_TX_CHAR_UUID, DEFAULT_UART_RX_CHAR_UUID))
            
            for service in client.services:
                print(f"\n[服務] UUID: {service.uuid}")
                write_chars = []
                notify_chars = []
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    print(f"  - [特徵] UUID: {char.uuid} | 屬性: [{props}]")
                    if "write" in props or "write-without-response" in props:
                        write_chars.append(char.uuid)
                    if "notify" in props:
                        notify_chars.append(char.uuid)
                
                for tx in write_chars:
                    for rx in notify_chars:
                        if (tx, rx) not in candidate_pairs:
                            candidate_pairs.append((tx, rx))
            
            print("-" * 50)
            
            # --- 階段二: 握手測試，尋找可用的 TX/RX 組合 ---
            print("[*] 階段二: 握手測試，尋找可用的通訊特徵...")
            working_tx_uuid: Optional[str] = None
            working_rx_uuid: Optional[str] = None

            for tx_uuid, rx_uuid in candidate_pairs:
                print(f"\n[*] 正在嘗試組合: \n    TX -> {tx_uuid}\n    RX -> {rx_uuid}")
                try:
                    await client.start_notify(rx_uuid, notification_handler)
                    response = await send_and_wait(client, tx_uuid, "ATZ")
                    
                    status, _ = interpret_response(response, "ATZ")
                    if status == "成功":
                        print(f"[+] 握手成功！回應: {response}")
                        working_tx_uuid = tx_uuid
                        working_rx_uuid = rx_uuid
                        break
                    else:
                        print(f"[-] 握手失敗: {status}")
                    
                    await client.stop_notify(rx_uuid)
                except Exception as e:
                    print(f"[-] 嘗試此組合時發生錯誤: {e}")

            if not (working_tx_uuid and working_rx_uuid):
                print("\n[!] 錯誤: 在所有候選組合中都未能找到可用的通訊特徵。")
                return

            print("-" * 50)
            print(f"[*] 已鎖定工作中的 UUIDs，開始執行標準測試流程...")

            # --- 階段三: 自動化指令測試 ---
            print("\n[*] 階段三: 自動化執行指令測試...")
            
            await run_test_case(client, working_tx_uuid, "設備重置", "ATZ")
            await run_test_case(client, working_tx_uuid, "關閉指令回顯", "ATE0")
            await run_test_case(client, working_tx_uuid, "查詢當前協議 (數字)", "ATDPN")
            await run_test_case(client, working_tx_uuid, "查詢支援的 PID (01-20)", "0100")
            await run_test_case(client, working_tx_uuid, "單一 PID 輪詢性能 (RPM)", "010C", iterations=10)
            await run_test_case(client, working_tx_uuid, "多重 PID 輪詢性能 (RPM, Speed, Temp, Volt)", "01 0C 0D 05 42", iterations=10)

            print("\n--- 所有測試已完成 ---")

    except Exception as e:
        print(f"\n[!] 發生未預期的錯誤: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] 程式已由使用者中斷。")

