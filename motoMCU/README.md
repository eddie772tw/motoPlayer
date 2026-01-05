# motoMCU

本目錄包含用於 MotoMCU 專案的韌體燒錄、測試與效能評測工具。

## 環境需求

在執行腳本之前，請確保已安裝以下工具：

- **Python 3.x**
- **PlatformIO Core**: 用於編譯與上傳 C++ 韌體。
- **esptool**: 用於燒錄 MicroPython 韌體與清除 Flash。
- **adafruit-ampy**: 用於將檔案上傳至 MicroPython 裝置。
- **pyserial**: 用於序列通訊與裝置重設。

安裝 Python 依賴：
```bash
pip install esptool adafruit-ampy pyserial
```

## 自動化燒錄與測試 (`flash_and_test.py`)

`flash_and_test.py` 是一個整合腳本，可自動化處理 C++ (Arduino/Framework) 與 MicroPython 韌體的燒錄、程式碼上傳及連線後測試。

### 主要功能
- **自動偵測串口**：自動尋找連接的 ESP8266 裝置。
- **支援多種模式**：可單獨測試 C++ 模式、MicroPython (MP) 模式，或兩者同時測試（`all`）。
- **流程自動化**：包含清除 Flash、寫入韌體、上傳 `main.py`（針對 MP）、硬體重設以及測試後的連線檢查。

### 使用方法
```bash
python flash_and_test.py --mode [cpp|mp|all] --port [COM_PORT] --ip [TARGET_IP]
```

- `--mode`: 測試模式。預設為 `all`。
- `--port`: 指定串口（例如 `COM3` 或 `/dev/ttyUSB0`）。若未指定則會嘗試自動偵測。
- `--ip`: 裝置預期連線後的 IP 地址。預設為 `192.168.9.2`。

---

## 效能評測工具 (`benchmark_tool.py`)

`benchmark_tool.py` 用於評估 MCU 伺服器的 HTTP 處理效能。

### 主要功能
- **併發請求測試**：模擬多個執行緒同時對裝置發起請求。
- **延遲與吞吐量分析**：計算平均延遲（Latency）與每秒請求數（RPS）。
- **預設測試路徑**：
    - `JSON API (Sensors)`: 測試 `/api/sensors` 目錄（輕量級資料）。
    - `HTML Page (Root)`: 測試 `/` 根目錄（較重的靜態內容）。

### 使用方法
```bash
python benchmark_tool.py [TARGET_IP]
```

- `TARGET_IP`: 裝置的 IP 地址。預設為 `192.168.9.2`。

### 輸出範例
執行後將顯示總請求數、成功率、RPS 以及延遲（Avg/Min/Max）。

---

## 注意事項
- 進行 MicroPython 測試前，請確保 `micropython/firmware.bin` 與 `micropython/main.py` 已存在於相對應路徑。
- 燒錄 C++ 韌體時，腳本會調用 `pio run -t upload`，請確保目錄結構符合 PlatformIO 規範。
