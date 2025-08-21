# OBD_test_RFCOMM.py
#
# 版本: 2.0 (Refactored to use RealOBD module)
# 目的: 此腳本已重構為 real_obd 模組的專用測試工具。
#      它會導入 RealOBD 類別，並使用其方法來進行連線、
#      初始化與互動式指令測試，以確保模組功能正常。

import logging
import time

# [MODIFIED] 直接從我們的主模組導入 RealOBD 類別
from real_obd import RealOBD

# =================================================================
# ---               測試設定 (請務必修改)                       ---
# =================================================================
# ELM327 適配器的 MAC 位址
TEST_DEVICE_ADDRESS = "66:1E:32:8A:55:2C"

def main():
    """主測試函式"""
    logging.info("--- RealOBD 模組互動式測試工具 v2.0 ---")
    
    # --- 階段一: 初始化 RealOBD 模組並連線 ---
    obd_sensor = RealOBD(mac_address=TEST_DEVICE_ADDRESS)
    
    try:
        # connect() 函式現在包含了完整的初始化與協議握手流程
        if obd_sensor.connect():
            logging.info("--- 連線與初始化成功！ ---")
        else:
            logging.error("--- 連線或初始化失敗，請檢查日誌輸出。 ---")
            return

        # --- 階段二: 互動式指令測試 ---
        print("\n" + "-" * 50)
        print("您現在可以開始進行互動測試。")
        print("可用指令:")
        print("  - data         : 執行一次 get_obd_data() 來獲取所有核心數據。")
        print("  - cmd <AT指令> : 發送一個自訂的 AT 或 PID 指令 (例如: cmd 0100)。")
        print("  - exit         : 結束程式。")
        print("-" * 50)

        while True:
            user_input = input("> 測試指令: ").strip()
            
            if user_input.lower() == 'exit':
                break
            
            elif user_input.lower() == 'data':
                logging.info("正在執行 get_obd_data()...")
                start_time = time.perf_counter()
                data = obd_sensor.get_obd_data()
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                
                log_message = (
                    f"耗時: {duration_ms:6.1f} ms | "
                    f"RPM:{data.rpm or 'N/A'} | "
                    f"Speed:{data.speed or 'N/A'} | "
                    f"Temp:{data.coolant_temp or 'N/A'} | "
                    f"Volt:{data.battery_voltage or 'N/A'} | "
                    f"Load:{data.engine_load or 'N/A'}% | "
                    f"Throttle:{data.throttle_pos or 'N/A'}%"
                )
                logging.info(log_message)

            elif user_input.lower().startswith('cmd '):
                command = user_input[4:].strip()
                if command:
                    logging.info(f"正在發送自訂指令: '{command}'...")
                    response = obd_sensor._send_command(command)
                    logging.info(f"收到回應: {response}")
                else:
                    logging.warning("指令為空，請在 'cmd' 後面加上您想發送的指令。")
            
            elif not user_input:
                continue

            else:
                logging.warning(f"無法識別的指令: '{user_input}'。請使用 'data', 'cmd <指令>', 或 'exit'。")

    except KeyboardInterrupt:
        logging.info("使用者手動中斷程式。")
    except Exception as e:
        logging.error(f"測試過程中發生未預期的錯誤: {e}")
    finally:
        logging.info("正在關閉連線...")
        if obd_sensor and obd_sensor.is_connected:
            obd_sensor.disconnect()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s][%(asctime)s]%(message)s')
    main()
