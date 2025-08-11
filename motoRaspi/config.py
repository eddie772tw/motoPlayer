# config.py

# --- OBD 感測器模式 ---
# 說明: 決定應用程式要使用的OBD數據來源。
# 選項:
#   'MOCK' - 使用 'mock_obd.py' 來生成模擬數據，適合開發和測試。
#   'REAL' - 使用 'real_obd.py' 來嘗試連接真實的OBD-II硬體設備。
#
# 注意: 當設定為 'REAL' 時，請確保硬體已正確連接，
#      且 'real_obd.py' 中的序列埠名稱 ('/dev/rfcomm0') 是正確的。
OBD_MODE = 'MOCK'

# --- 真實 OBD 設備設定 (僅在 OBD_MODE = 'REAL' 時有效) ---
REAL_OBD_PORT = '/dev/rfcomm0'
REAL_OBD_BAUDRATE = 38400
