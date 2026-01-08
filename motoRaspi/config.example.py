# Copyright (C) 2026 eddie772tw
# This file is part of motoPlayer.
# motoPlayer is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# config.py (RFCOMM)

# --- OBD-II 連線模式設定 ---
OBD_MODE = 'REAL' # 可選值: 'REAL', 'MOCK'

# --- 真實 OBD (RFCOMM) 設定 ---
OBD_DEVICE_ADDRESS = "00:00:00:00:00:00"  # 您的 OBD 適配器 MAC 位址
RFCOMM_CHANNEL = 1 # RFCOMM 通道，通常是 1


# --- DMX 設定 ---
DMX_MAC_ADDRESS = "00:00:00:00:00:00"
