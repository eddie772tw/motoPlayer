# MotoPlayer

**MotoPlayer** 是一個整合式的智慧車載遙測與娛樂系統，專為機車（或汽車）設計。本專案結合了 Raspberry Pi 的強大運算能力與 MCU 的即時控制特性，提供即時的車輛數據監控、智慧燈光控制以及多媒體互動功能。

## 專案架構

本系統由三個主要部分組成，分別負責不同的功能層級：

### 1. 核心運算單元 (`motoRaspi`)
- **平台**: Raspberry Pi (Debian/Raspberry Pi OS)
- **語言**: Python 3.12
- **框架**: Flask, Flask-SocketIO, APScheduler
- **功能**:
  - **OBD-II 介面**: 透過藍牙 (RFCOMM) 與 ELM327 適配器通訊，即時讀取 RPM、時速、引擎負載、電瓶電壓等數據。
  - **Web 儀表板**: 提供 WebSocket 即時數據串流的前端介面。
  - **DMX 控制**: 支援 DMX512 燈光控制協議。
  - **資料庫**: 使用 SQLite 紀錄行車數據 (Telemetry)。

### 2. 無線感測與控制節點 (`motoMCU`)
- **平台**: ESP8266 (NodeMCU v2)
- **開發環境**: PlatformIO (C++/Arduino Framework) & MicroPython
- **功能**:
  - 無線感測器數據回傳。
  - 支援 OTA (Over-The-Air) 韌體更新。
  - 包含自動化燒錄與效能測試工具 (`flash_and_test.py`, `benchmark_tool.py`)。

### 3. 硬體周邊控制 (`motoUNO`)
- **平台**: Arduino Uno
- **開發環境**: PlatformIO (Arduino Framework)
- **功能**:
  - **硬體交互**: 處理 RFID 讀卡 (MFRC522)。
  - **音效輸出**: 控制 DFPlayer Mini 播放音效。
  - **環境感測**: 讀取 DHT 溫濕度傳感器。

---

## 目錄結構說明

```text
motoPlayer/
├── motoRaspi/          # Raspberry Pi 後端應用程式、設定檔與安裝腳本
│   ├── app/            # Flask 應用程式原始碼
│   ├── config.example.py # 設定檔範本 (請複製並重新命名為 config.py)
│   ├── setup.md        #詳細環境安裝與設定指南
│   ├── real_obd.py     # 真實 OBD-II 連線邏輯
│   └── ...
├── motoMCU/            # ESP8266 韌體專案 (PlatformIO)
│   ├── src/            # C++ 原始碼
│   ├── micropython/    # MicroPython 相關腳本
│   └── ...
├── motoUNO/            # Arduino Uno 韌體專案 (PlatformIO)
└── moto_env/           # (Local) Python 虛擬環境目錄 (git ignored)
```

## 快速開始

### 1. Raspberry Pi 環境設定 (`motoRaspi`)

請依照 `motoRaspi/setup.md` 中的步驟進行設定。主要流程包括：
1. 安裝系統依賴 (Python 3, Bluetooth 等)。
2. 建立 Python 虛擬環境 (`moto_env`)。
3. 安裝 Python 套件: `pip install -r motoRaspi/requirements.txt`。
4. 設定檔配置：
   ```bash
   cp motoRaspi/config.example.py motoRaspi/config.py
   # 編輯 config.py 填入您的 OBD-II MAC Address 與其他設定
   ```
5. 初始化資料庫: `python motoRaspi/init_db.py`。
6. 啟動伺服器: `python motoRaspi/run.py`。

### 2. MCU 韌體燒錄 (`motoMCU` / `motoUNO`)

本專案使用 **PlatformIO** 進行 MCU 開發。請確保您已安裝 VS Code 與 PlatformIO Extension。

- **motoMCU (ESP8266)**:
  - 進入 `motoMCU` 目錄。
  - 使用 PlatformIO Upload 功能燒錄韌體。
  - 或使用提供的工具腳本 `python flash_and_test.py` 進行自動化測試與燒錄。

- **motoUNO (Arduino)**:
  - 進入 `motoUNO` 目錄。
  - 使用 PlatformIO Upload 功能燒錄韌體。

## 開發與貢獻

歡迎提交 Pull Request 或 Issue。在提交程式碼前，請確保：
- 不包含任何個人敏感資訊 (如 MAC Address、WiFi 密碼等)。
- 更新相關的文檔與註解。
- 確認 `.gitignore` 涵蓋了所有編譯產生的暫存檔。

## 授權

本專案採用 MIT License。詳情請參閱 LICENSE 文件 (如有提供)。
