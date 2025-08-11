#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
這是一個互動式的設定腳本，用於自動化完成藍牙 OBD-II 裝置的首次配對與 rfcomm 服務的建立。
v2.0: 新增 RSSI 排序與無名稱裝置過濾功能。
"""

import os
import sys
import subprocess
import time
import re

def check_sudo():
    """檢查腳本是否以 sudo 權限執行。"""
    if os.geteuid() != 0:
        print("錯誤：此腳本需要以 sudo 權限執行。")
        print("請嘗試使用 'sudo python3 bt_setup.py' 來執行。")
        sys.exit(1)
    print("權限檢查通過。")

def scan_devices(scan_duration=10):
    """
    掃描藍牙裝置，過濾、排序後返回一個包含裝置資訊的列表。
    """
    print(f"正在掃描附近的藍牙裝置，請稍候 {scan_duration} 秒...")
    devices = {}
    # 正規表示式，用於從 'scan on' 的輸出中匹配 MAC, RSSI 和名稱
    device_pattern = re.compile(r"Device ([0-9A-Fa-f:]{17}) (.*)")
    rssi_pattern = re.compile(r"\[CHG\] Device ([0-9A-Fa-f:]{17}) RSSI: (-?\d+)")

    try:
        with subprocess.Popen(
            ['bluetoothctl'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        ) as p:
            p.stdin.write("scan on\n")
            p.stdin.flush()
            
            start_time = time.time()
            while time.time() - start_time < scan_duration:
                line = p.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                # 嘗試匹配 RSSI
                rssi_match = rssi_pattern.search(line)
                if rssi_match:
                    mac, rssi = rssi_match.groups()
                    if mac not in devices:
                        devices[mac] = {'mac': mac, 'name': None, 'rssi': -999}
                    devices[mac]['rssi'] = int(rssi)
                    continue

                # 嘗試匹配裝置名稱
                device_match = device_pattern.search(line)
                if device_match:
                    mac, name = device_match.groups()
                    if mac not in devices:
                        devices[mac] = {'mac': mac, 'name': None, 'rssi': -999}
                    # 只有當名稱不是單純的MAC位址時才更新
                    if name != mac:
                        devices[mac]['name'] = name

            p.stdin.write("scan off\n")
            p.stdin.flush()
            p.stdin.close()
            p.wait(timeout=5)

        # --- 處理掃描結果 ---
        device_list = list(devices.values())

        # 1. 過濾: 只保留有名稱的裝置
        filtered_list = [dev for dev in device_list if dev.get('name')]
        
        if not filtered_list:
            print("掃描完成，未發現任何具備名稱的裝置。")
            return []

        # 2. 排序: 依照 RSSI 由強至弱排序
        sorted_list = sorted(filtered_list, key=lambda x: x['rssi'], reverse=True)

        print("掃描完成。發現以下裝置 (已依訊號強度排序)：")
        for i, dev in enumerate(sorted_list, 1):
            print(f"  {i}: {dev['name']} ({dev['mac']}) [訊號強度: {dev['rssi']} dBm]")

        return sorted_list

    except FileNotFoundError:
        print("錯誤：找不到 'bluetoothctl' 命令。請確認 bluez 套件已安裝。")
        sys.exit(1)
    except Exception as e:
        print(f"掃描時發生未預期的錯誤：{e}")
        sys.exit(1)


def select_device(devices):
    """
    提示使用者從列表中選擇一個裝置，並返回選擇的裝置字典。
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
                print(f"您已選擇: {selected_device['name']} ({selected_device['mac']})")
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
    """
    print(f"\n正在設定裝置 {mac_address}...")
    try:
        with subprocess.Popen(
            ['bluetoothctl'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        ) as p:
            def read_output_until(phrases, timeout=20):
                start_time = time.time()
                output_lines = []
                while time.time() - start_time < timeout:
                    line = p.stdout.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    output_lines.append(line)
                    print(f"  [BT] {line.strip()}")
                    for phrase in phrases:
                        if phrase in line:
                            return phrase, "".join(output_lines)
                return None, "".join(output_lines)

            print("\n步驟 1/3: 正在移除舊的裝置設定 (若有)...")
            p.stdin.write(f"remove {mac_address}\n")
            p.stdin.flush()
            read_output_until(["Device has been removed", "Device not available"], timeout=5)
            print("舊設定已清除。")

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
    except Exception as e:
        print(f"處理藍牙裝置時發生未預期的錯誤: {e}")
        return False


def create_rfcomm_service(mac_address):
    """
    建立並寫入 rfcomm 的 systemd 服務檔案。
    """
    service_path = "/etc/systemd/system/rfcomm.service"
    print(f"\n正在為 {mac_address} 建立 systemd 服務...")
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
    except Exception as e:
        print(f"建立服務檔案時發生未預期的錯誤：{e}")
        return False


def run_system_command(command):
    """執行一個系統命令並回傳其成功狀態。"""
    try:
        print(f"  [CMD] {' '.join(command)}")
        subprocess.run(command, check=True, text=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"錯誤：命令 '{' '.join(command)}' 執行失敗。")
        print(f"  錯誤輸出: {e.stderr.strip()}")
        return False
    except Exception as e:
        print(f"執行命令時發生未預期的錯誤：{e}")
        return False

def enable_and_start_service():
    """
    執行 systemctl daemon-reload 並啟用與啟動 rfcomm 服務。
    """
    print("\n正在啟用並啟動 systemd 服務...")
    if not run_system_command(['systemctl', 'daemon-reload']): return False
    if not run_system_command(['systemctl', 'enable', 'rfcomm.service']): return False
    if not run_system_command(['systemctl', 'start', 'rfcomm.service']):
        print("啟動 rfcomm 服務失敗。正在檢查服務狀態...")
        run_system_command(['systemctl', 'status', 'rfcomm.service'])
        return False
    print("\n✔ rfcomm 服務已成功啟用並啟動！")
    return True


def main():
    """主執行函數"""
    try:
        check_sudo()
        print("="*50)
        print("藍牙 OBD-II 裝置自動設定腳本 (v2.0 - RSSI 排序)")
        print("="*50)

        discovered_devices = scan_devices()
        if not discovered_devices:
            sys.exit(0)

        selected_device = select_device(discovered_devices)
        if not selected_device:
            sys.exit(0)

        mac, name = selected_device['mac'], selected_device['name']
        if pair_and_trust_device(mac):
            print(f"\n✔ 裝置 {name} ({mac}) 已成功配對並信任。")
            if create_rfcomm_service(mac):
                if enable_and_start_service():
                    print("\n🎉 設定完成！您的藍牙 OBD-II 裝置已準備就緒。")
                else:
                    print("\n啟用服務失敗，請檢查上述錯誤訊息。")
                    sys.exit(1)
            else:
                sys.exit(1)
        else:
            sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\n\n操作被使用者中斷，腳本退出。")
        sys.exit(1)


if __name__ == "__main__":
    main()

