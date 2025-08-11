import requests
import time
import socket

# =================================================================
# --- 設定 (Configuration) ---
# =================================================================
NODEMCU_HOSTNAME = "motoplayer.local"
POLLING_INTERVAL_SECONDS = 2.5

# [修改] 簡化指令映射，移除需要參數的指令
COMMANDS_MAP = {
    "vol+": "/api/vol_up",
    "vol-": "/api/vol_down",
    "stop_blink": "/api/stop_blink",
    "restart": "/api/restart",
}


# =================================================================
# --- 函式定義 (Function Definitions) ---
# =================================================================

def get_mcu_ip():
    """解析 mDNS 名稱以獲取 IP 位址"""
    try:
        ip = socket.gethostbyname(NODEMCU_HOSTNAME)
        return ip
    except socket.gaierror:
        print(f"[ERROR] 無法解析主機名稱 '{NODEMCU_HOSTNAME}'。")
        return None


def send_command_to_mcu(command, param=None):
    """向 NodeMCU 發送一個指令"""
    mcu_ip = get_mcu_ip()
    if not mcu_ip:
        return

    base_url = f"http://{mcu_ip}"
    api_path = ""

    # [修改] 增強指令解析和 API 路徑組合邏輯
    if command == "play" and param and param.isdigit():
        api_path = f"/api/play?track={param}"
    elif command in ["blink", "on", "off"] and param in ['g', 'b']:
        # 組合出 /api/blink_g, /api/on_b 這樣的路徑
        api_path = f"/api/{command}_{param}"
    elif command in COMMANDS_MAP:
        api_path = COMMANDS_MAP[command]
    else:
        print(f"錯誤：未知或格式不正確的指令 '{command}{' ' + param if param else ''}'")
        return

    full_url = base_url + api_path

    try:
        if command == "restart":
            confirm = input("您確定要重啟 NodeMCU+UNO 系統嗎？[y/N]: ").lower()
            if confirm != 'y':
                print("操作已取消。")
                return

        print(f"正在發送指令到: {full_url} ...")
        response = requests.get(full_url, timeout=5)

        if response.status_code == 200:
            print(f"成功！ NodeMCU 回應: {response.text}")
        else:
            print(f"失敗！ NodeMCU 回應狀態碼: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"錯誤：網路請求失敗 - {e}")


def print_help():
    """印出所有可用的指令"""
    print("\n" + "=" * 15 + " 指令列表 " + "=" * 15)
    print("  play <數字>      - 播放指定編號的音軌 (例如: play 3)")
    print("  vol+ / vol-      - 音量增大 / 減小")
    print("  blink <g/b>      - 閃爍指定顏色的燈 (例如: blink g)")
    print("  on <g/b>         - 開啟指定顏色的燈 (例如: on b)")
    print("  off <g/b>        - 關閉指定顏色的燈 (例如: off g)")
    print("  stop_blink       - 停止所有閃爍，並熄滅LED")
    print("  restart          - 重啟 NodeMCU+UNO 系統")
    print("  help             - 顯示此幫助訊息")
    print("  exit             - 退出此程式")
    print("=" * 42 + "\n")


# =================================================================
# --- 主程式進入點 (Main Execution) ---
# =================================================================

if __name__ == "__main__":
    print("--- MotoNodeMCU CLI v2.0 (Unified Command Format) ---")
    print("輸入 'help' 來查看所有可用指令。")

    while True:
        try:
            user_input = input("CMD> ").strip().lower()
        except KeyboardInterrupt:
            print("\n再見！")
            break

        if not user_input:
            continue

        if user_input == "exit":
            break

        if user_input == "help":
            print_help()
            continue

        # 解析指令和參數
        parts = user_input.split()
        command = parts[0]
        parameter = None
        if len(parts) > 1:
            parameter = parts[1]

        send_command_to_mcu(command, parameter)

    print("CLI 已關閉。")