# check_bleak.py

import sys

print("--- Bleak Library Diagnostic ---")

try:
    import bleak
    print(f"✅ Bleak 模組匯入成功")
except Exception as e:
    print(f"❌ 嚴重錯誤: 連 'import bleak' 都失敗了: {e}")
    sys.exit(1)

# 1. 檢查版本
print(f"\n[1] 偵測到的 Bleak 版本: {bleak.}")

# 2. 檢查檔案路徑
print(f"[2] Bleak 模組路徑: {bleak.__file__}")

# 3. 列出所有可用的頂層名稱
print("\n[3] Bleak 頂層命名空間中所有可用的名稱:")
bleak_contents = dir(bleak)
for name in sorted(bleak_contents):
    print(f"  - {name}")

# 4. 檢查 BleakServer 是否在其中
print("\n[4] 最終檢查...")
if "BleakServer" in bleak_contents:
    print("✅ 'BleakServer' 存在於 Bleak 的頂層命名空間中。")
    print("   理論上 'from bleak import BleakServer' 應該要能成功。")
else:
    print("❌ 'BleakServer' **不存在**於 Bleak 的頂層命名空間中。")
    print("   這證實了您的安裝可能已損毀或版本不符。")

print("\n--- Diagnostic Complete ---")