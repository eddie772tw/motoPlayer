# Copyright (C) 2026 eddie772tw
# This file is part of motoPlayer.
# motoPlayer is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# init_db.py
import sqlite3
import os

DATABASE_NAME = "motoplayer.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_NAME)

def migrate_database(conn):
    """
    執行資料庫遷移，新增所有在 OBDData v4.0 模型中定義的新欄位。
    這個函式是冪等的，可以安全地重複執行。
    """
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(telemetry_data);")
        columns = [row[1] for row in cursor.fetchall()]

        # 定義所有應該存在的 OBD 欄位及其類型
        # 注意：我們將不再使用 'gear' 欄位
        obd_fields = {
            'throttle_pos': 'REAL',
            'engine_load': 'REAL',
            'abs_load_val': 'REAL',
            'timing_advance': 'REAL',
            'intake_air_temp': 'REAL',
            'intake_map': 'INTEGER',
            'fuel_system_status': 'TEXT',
            'short_term_fuel_trim_b1': 'REAL',
            'long_term_fuel_trim_b1': 'REAL',
            'o2_sensor_voltage_b1s1': 'REAL'
        }

        for field, field_type in obd_fields.items():
            if field not in columns:
                print(f"正在為 `telemetry_data` 新增 `{field}` 欄位...")
                cursor.execute(f"ALTER TABLE telemetry_data ADD COLUMN {field} {field_type};")
                print(f"`{field}` 欄位新增成功。")

        conn.commit()

    except sqlite3.Error as e:
        print(f"[MIGRATE ERROR] 新增欄位時發生錯誤: {e}")

def initialize_database():
    """
    初始化資料庫。如果資料庫或資料表不存在，則會創建它們。
    """
    print(f"正在檢查並初始化資料庫: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        print("成功連接到資料庫。")
        
        # CREATE TABLE 陳述式已更新，移除了 gear 並加入了核心 OBD 欄位
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS telemetry_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            trip_id INTEGER,
            uno_status TEXT,
            rfid_card TEXT,
            temperature REAL,
            humidity REAL,
            light_level INTEGER,
            rpm INTEGER,
            speed INTEGER,
            coolant_temp REAL,
            battery_voltage REAL
        );
        """
        cursor = conn.cursor()
        cursor.execute(create_table_sql)
        print("`telemetry_data` 資料表已成功建立或已存在。")
        
        # 執行遷移，以確保所有新欄位都被加入到既有的資料表中
        migrate_database(conn)

        conn.close()
        print("資料庫初始化完成，連接已關閉。")
    except sqlite3.Error as e:
        print(f"[DATABASE ERROR] 初始化資料庫時發生錯誤: {e}")

if __name__ == '__main__':
    initialize_database()
