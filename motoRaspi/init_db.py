# init_db.py (更新後的版本)
import sqlite3
import os

DATABASE_NAME = "motoplayer.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_NAME)

def migrate_database(conn):
    """
    執行資料庫遷移，例如新增欄位。
    """
    cursor = conn.cursor()
    try:
        # 檢查 trip_id 欄位是否存在，不存在才新增
        cursor.execute("PRAGMA table_info(telemetry_data);")
        columns = [row[1] for row in cursor.fetchall()]
        if 'trip_id' not in columns:
            print("正在為 `telemetry_data` 新增 `trip_id` 欄位...")
            cursor.execute("ALTER TABLE telemetry_data ADD COLUMN trip_id INTEGER;")
            conn.commit()
            print("`trip_id` 欄位新增成功。")
        else:
            print("`trip_id` 欄位已存在，無需新增。")
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
        
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS telemetry_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            trip_id INTEGER, -- 預留 trip_id 欄位
            uno_status TEXT,
            rfid_card TEXT,
            temperature REAL,
            humidity REAL,
            light_level INTEGER,
            rpm INTEGER,
            speed INTEGER,
            coolant_temp REAL,
            battery_voltage REAL,
            gear INTEGER
        );
        """
        cursor = conn.cursor()
        cursor.execute(create_table_sql)
        print("`telemetry_data` 資料表已成功建立或已存在。")
        
        # 執行遷移
        migrate_database(conn)

        conn.close()
        print("資料庫初始化完成，連接已關閉。")
    except sqlite3.Error as e:
        print(f"[DATABASE ERROR] 初始化資料庫時發生錯誤: {e}")

if __name__ == '__main__':
    initialize_database()