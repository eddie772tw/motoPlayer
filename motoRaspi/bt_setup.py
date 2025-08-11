#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
這是一個互動式的設定腳本，用於自動化完成藍牙 OBD-II 裝置的首次配對與 rfcomm 服務的建立。
"""

import os
import sys
import subprocess
import time

def check_sudo():
    """檢查腳本是否以 sudo 權限執行。"""
    if os.geteuid() != 0:
        print("錯誤：此腳本需要以 sudo 權限執行。")
        print("請嘗試使用 'sudo python3 bt_setup.py' 來執行。")
        sys.exit(1)
    print("權限檢查通過。")

import re

def scan_devices(scan_duration=10):
    """
    掃描藍牙裝置並返回一個包含 (MAC, 名稱) 的列表。
    """
    print(f"正在掃描附近的藍牙裝置，請稍候 {scan_duration} 秒...")
    devices = {}
    # 正規表示式，用於匹配 MAC 位址
    mac_pattern = re.compile(r"([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})")

    try:
        # 使用 Popen 啟動 bluetoothctl
        with subprocess.Popen(
            ['bluetoothctl'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # 行緩衝
        ) as p:

            # 開始掃描
            p.stdin.write("scan on\n")
            p.stdin.flush()
            time.sleep(scan_duration)

            # 停止掃描
            p.stdin.write("scan off\n")
            p.stdin.flush()

            # 獲取裝置列表
            p.stdin.write("devices\n")
            p.stdin.flush()

            # 關閉 stdin，表示指令發送完畢
            p.stdin.close()

            # 讀取輸出並解析裝置資訊
            for line in p.stdout:
                if "Device" in line:
                    match = mac_pattern.search(line)
                    if match:
                        mac_address = match.group(0)
                        # MAC 位址之後的字串為裝置名稱
                        name = line.split(mac_address, 1)[1].strip()
                        devices[mac_address] = name

        if not devices:
            print("掃描完成，未發現任何裝置。")
            return []

        print("掃描完成。發現以下裝置：")
        # 將字典轉換為列表以便編號
        device_list = list(devices.items())
        for i, (mac, name) in enumerate(device_list, 1):
            print(f"  {i}: {name} ({mac})")

        return device_list

    except FileNotFoundError:
        print("錯誤：找不到 'bluetoothctl' 命令。請確認 bluez 套件已安裝。")
        sys.exit(1)
    except Exception as e:
        print(f"掃描時發生未預期的錯誤：{e}")
        sys.exit(1)


def select_device(devices):
    """
    提示使用者從列表中選擇一個裝置，並返回選擇的裝置 (MAC, 名稱)。
    """
    if not devices:
        return None

    while True:
        try:
            choice_str = input("請輸入您要設定的裝置編號：")
            if not choice_str:
                continue

            choice_index = int(choice_str) - 1

            if 0 <= choice_index < len(devices):
                selected_device = devices[choice_index]
                mac, name = selected_device
                print(f"您已選擇: {name} ({mac})")
                return selected_device
            else:
                print(f"輸入無效。請輸入 1 到 {len(devices)} 之間的數字。")

        except ValueError:
            print("輸入無效，請輸入一個數字。")
        except (KeyboardInterrupt, EOFError):
            print("\n操作已取消，腳本退出。")
            sys.exit(1)


def pair_and_trust_device(mac_address):
    """
    與指定的 MAC 位址進行配對和信任操作。
    使用一個持續的 Popen 程序來處理互動。
    """
    print(f"\n正在設定裝置 {mac_address}...")
    try:
        with subprocess.Popen(
            ['bluetoothctl'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 將 stderr 重導向至 stdout
            text=True,
            bufsize=1
        ) as p:

            def read_output_until(phrases, timeout=20):
                """從程序讀取輸出，直到找到特定片語或超時。"""
                start_time = time.time()
                output_lines = []
                while time.time() - start_time < timeout:
                    line = p.stdout.readline()
                    if not line:
                        time.sleep(0.1)
                        continue

                    output_lines.append(line)
                    print(f"  [BT] {line.strip()}")  # 提供即時回饋

                    for phrase in phrases:
                        if phrase in line:
                            return phrase, "".join(output_lines)

                return None, "".join(output_lines)

            # 步驟 1: 為了確保全新狀態，先嘗試移除裝置
            print("\n步驟 1/3: 正在移除舊的裝置設定 (若有)...")
            p.stdin.write(f"remove {mac_address}\n")
            p.stdin.flush()
            read_output_until(["Device has been removed", "Device not available"], timeout=5)
            print("舊設定已清除。")

            # 步驟 2: 配對與信任
            print("\n步驟 2/3: 正在嘗試與裝置配對...")
            p.stdin.write(f"pair {mac_address}\n")
            p.stdin.flush()

            result, output = read_output_until(
                ["Pairing successful", "Failed to pair", "Device is already paired", "[agent] Enter PIN code"],
                timeout=25
            )

            if result == "[agent] Enter PIN code":
                pin = input("請輸入 PIN 碼 (預設為 '1234'): ") or "1234"
                print(f"正在使用 PIN: {pin}")
                p.stdin.write(f"{pin}\n")
                p.stdin.flush()
                result, output = read_output_until(["Pairing successful", "Failed to pair"], timeout=15)

            if result not in ["Pairing successful", "Device is already paired"]:
                print(f"錯誤：配對失敗。\n藍牙輸出:\n{output}")
                return False

            print("✔ 配對成功！")

            print("\n步驟 3/3: 正在設定裝置為信任...")
            p.stdin.write(f"trust {mac_address}\n")
            p.stdin.flush()

            result, output = read_output_until(["trust succeeded", "Failed to trust"], timeout=10)

            if "trust succeeded" not in (result or ""):
                 p.stdin.write(f"info {mac_address}\n")
                 p.stdin.flush()
                 info_result, info_output = read_output_until(["Trusted: yes", "Trusted: no"], timeout=5)
                 if info_result != "Trusted: yes":
                    print(f"錯誤：信任失敗。\n藍牙輸出:\n{output}{info_output}")
                    return False

            print("✔ 裝置信任成功！")

            p.stdin.write("exit\n")
            p.stdin.flush()
            p.wait(timeout=5)

            return True

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"與 bluetoothctl 互動時發生錯誤: {e}")
        return False
    except Exception as e:
        print(f"處理藍牙裝置時發生未預期的錯誤: {e}")
        return False


def create_rfcomm_service(mac_address):
    """
    建立並寫入 rfcomm 的 systemd 服務檔案。
    """
    service_path = "/etc/systemd/system/rfcomm.service"
    print(f"\n正在為 {mac_address} 建立 systemd 服務...")

    # 動態生成服務檔案內容
    service_content = f"""[Unit]
Description=RFCOMM TTY for Bluetooth device {mac_address}
After=bluetooth.target
Requires=bluetooth.target

[Service]
Type=simple
ExecStart=/usr/bin/rfcomm bind 0 {mac_address} 1
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
"""

    try:
        print(f"正在將服務檔案寫入到 {service_path}...")
        with open(service_path, "w") as f:
            f.write(service_content.strip())

        print(f"✔ systemd 服務檔案 '{service_path}' 建立成功！")
        return True
    except (IOError, PermissionError) as e:
        print(f"錯誤：無法寫入服務檔案 {service_path}。")
        print(f"請確認您是否使用 sudo 權限執行，且該路徑可寫入。")
        print(f"詳細錯誤：{e}")
        return False
    except Exception as e:
        print(f"建立服務檔案時發生未預期的錯誤：{e}")
        return False


def run_system_command(command, capture_output=False):
    """執行一個系統命令並回傳其成功狀態及輸出。"""
    try:
        print(f"  [CMD] {' '.join(command)}")
        result = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=capture_output
        )
        return True, result.stdout if capture_output else ""
    except subprocess.CalledProcessError as e:
        print(f"錯誤：命令 '{' '.join(command)}' 執行失敗。")
        print(f"  返回碼: {e.returncode}")
        if e.stdout:
            print(f"  標準輸出: {e.stdout.strip()}")
        if e.stderr:
            print(f"  錯誤輸出: {e.stderr.strip()}")
        return False, e.stderr
    except FileNotFoundError:
        print(f"錯誤：找不到命令 '{command[0]}'。請確認相關套件已安裝且在系統 PATH 中。")
        return False, ""
    except Exception as e:
        print(f"執行命令時發生未預期的錯誤：{e}")
        return False, ""

def enable_and_start_service():
    """
    執行 systemctl daemon-reload 並啟用與啟動 rfcomm 服務。
    """
    print("\n正在啟用並啟動 systemd 服務...")

    print("\n步驟 1/3: 重新載入 systemd 設定...")
    if not run_system_command(['systemctl', 'daemon-reload'])[0]:
        print("重新載入 systemd 設定失敗。")
        return False

    print("\n步驟 2/3: 啟用服務，使其開機自啟...")
    if not run_system_command(['systemctl', 'enable', 'rfcomm.service'])[0]:
        print("啟用 rfcomm 服務失敗。")
        return False

    print("\n步驟 3/3: 立即啟動服務...")
    if not run_system_command(['systemctl', 'start', 'rfcomm.service'])[0]:
        print("啟動 rfcomm 服務失敗。正在檢查服務狀態...")
        run_system_command(['systemctl', 'status', 'rfcomm.service'])
        return False

    print("\n✔ rfcomm 服務已成功啟用並啟動！")
    print("您現在應該可以透過 /dev/rfcomm0 存取您的藍牙裝置。")
    print("服務目前狀態:")
    run_system_command(['systemctl', 'is-active', 'rfcomm.service'])
    return True


def main():
    """主執行函數"""
    try:
        check_sudo()
        print("="*50)
        print("藍牙 OBD-II 裝置自動設定腳本")
        print("="*50)

        discovered_devices = scan_devices()

        if not discovered_devices:
            print("\n未發現任何裝置，腳本結束。")
            sys.exit(0)

        selected_device = select_device(discovered_devices)

        if not selected_device:
            print("\n未選擇任何裝置，腳本結束。")
            sys.exit(0)

        mac, name = selected_device
        if pair_and_trust_device(mac):
            print(f"\n✔ 裝置 {name} ({mac}) 已成功配對並信任。")
            if create_rfcomm_service(mac):
                if enable_and_start_service():
                    print("\n🎉 設定完成！您的藍牙 OBD-II 裝置已準備就緒。")
                else:
                    print("\n啟用服務失敗，請檢查上述錯誤訊息。")
                    sys.exit(1)
            else:
                print("\n建立 systemd 服務失敗，請檢查錯誤訊息。")
                sys.exit(1)
        else:
            print(f"\n設定裝置 {name} ({mac}) 失敗。")
            sys.exit(1)

    except (KeyboardInterrupt, EOFError):
        print("\n\n操作被使用者中斷，腳本退出。")
        sys.exit(1)
    except Exception as e:
        print(f"\n發生未預期的嚴重錯誤：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
