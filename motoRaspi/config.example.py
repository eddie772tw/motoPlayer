# config.py (RFCOMM)

# --- OBD-II 連線模式設定 ---
OBD_MODE = 'REAL' # 可選值: 'REAL', 'MOCK'

# --- 真實 OBD (RFCOMM) 設定 ---
OBD_DEVICE_ADDRESS = "00:00:00:00:00:00"  # 您的 OBD 適配器 MAC 位址
RFCOMM_CHANNEL = 1 # RFCOMM 通道，通常是 1


# --- DMX 設定 ---
DMX_MAC_ADDRESS = "00:00:00:00:00:00"
