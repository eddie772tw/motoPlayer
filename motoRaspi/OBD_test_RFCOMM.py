# OBD_test_RFCOMM.py
#
# 版本: 1.1 (Automated Diagnostics)
# 目的: 參考 pyobd-pi 專案的思路，使用 PyBluez 函式庫直接建立傳統藍牙
#      RFCOMM Socket 連線。此版本在連線後會自動執行一組診斷指令，
#      然後再進入互動測試模式。

import sys
import bluetooth
import time

# =================================================================
# ---               藍牙連線參數 (請務必修改)                   ---
# =================================================================
# ELM327 適配器的 MAC 位址
OBD_DEVICE_ADDRESS = "66:1E:32:8A:55:2C"  # 請替換成您的設備位址

# RFCOMM 的通訊頻道 (Port/Channel)，對於序列埠設定檔(SPP)通常是 1
RFCOMM_CHANNEL = 1

# =================================================================

def send_and_receive(sock, command):
    """一個輔助函式，用於發送指令並接收完整的回應。"""
    print(f"> 指令: {command}")
    sock.send((command + '\r').encode('utf-8'))
    
    response_buffer = ""
    try:
        while True:
            data = sock.recv(1024)
            if not data:
                break
            response_buffer += data.decode('utf-8', errors='ignore')
            # ELM327 的回應以 '>' 結尾
            if '>' in response_buffer:
                break
        print(f"< 回應: {response_buffer.strip()}")
        return response_buffer.strip()
    except bluetooth.btcommon.BluetoothError as e:
        if "timed out" in str(e):
            print("< 回應: 操作超時 (5秒內未收到 '>' 結束符)。")
        else:
            raise e
    return ""


def main():
    """主測試函式"""
    print("--- ELM327 RFCOMM Socket 互動式指令測試工具 v1.1 ---")

    # --- 階段一: 掃描設備 ---
    print("\n[*] 階段一: 正在掃描附近的傳統藍牙設備...")
    try:
        nearby_devices = bluetooth.discover_devices(duration=3, lookup_names=True, flush_cache=True)
        print(f"[+] 掃描完成，發現 {len(nearby_devices)} 個設備。")
        
        target_device_found = False
        for addr, name in nearby_devices:
            print(f"  - 位址: {addr}, 名稱: {name}")
            if addr == OBD_DEVICE_ADDRESS:
                print(f"  [*] 已成功找到目標設備: {name} ({addr})")
                target_device_found = True
        
        if not target_device_found:
            print(f"\n[!] 警告: 在掃描結果中未找到指定的設備位址 ({OBD_DEVICE_ADDRESS})。")
            print("[!] 請確認設備已通電且處於可配對模式。腳本將繼續嘗試連線...")

    except Exception as e:
        print(f"[!] 掃描過程中發生錯誤: {e}")
        return

    # --- 階段二: 建立 Socket 連線與自動化診斷 ---
    print(f"\n[*] 階段二: 正在嘗試連線到 {OBD_DEVICE_ADDRESS} 的 RFCOMM 頻道 {RFCOMM_CHANNEL}...")
    
    sock = None
    try:
        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        sock.connect((OBD_DEVICE_ADDRESS, RFCOMM_CHANNEL))
        sock.settimeout(5.0)
        print("[+] 連線成功！")
        print("-" * 40)
        
        # [NEW] 自動化診斷序列
        print("[*] 正在執行自動化診斷序列...")
        
        # 清空可能存在的初始緩衝區數據
        time.sleep(0.5)
        sock.recv(1024)

        send_and_receive(sock, "ATZ")
        send_and_receive(sock, "ATRV")
        send_and_receive(sock, "ATSP0")
        send_and_receive(sock, "ATDPN")
        send_and_receive(sock, "0100")
        
        print("[+] 自動化診斷序列執行完畢。")
        print("-" * 40)

    except Exception as e:
        print(f"[!] 連線或診斷過程中失敗: {e}")
        if sock:
            sock.close()
        return

    # --- 階段三: 互動式指令測試 ---
    try:
        print("\n[*] 階段三: 您現在可以開始手動輸入指令 (輸入 'exit' 來結束程式)。")
        while True:
            command = input("> 手動指令: ")
            if command.lower() == 'exit':
                break
            if not command:
                continue
            
            send_and_receive(sock, command)

    except Exception as e:
        print(f"\n[!] 通訊過程中發生錯誤: {e}")
    finally:
        print("[*] 正在關閉連線...")
        if sock:
            sock.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] 程式已由使用者中斷。")

