import sqlite3
import serial
import json
import time
from datetime import datetime

# --- 설정 ---
DB_NAME = "smart_home.db"
SERIAL_PORT = 'COM3'  # 포트 번호 확인 필수!
BAUD_RATE = 115200    

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 스키마 변경: win_stat, heat_stat, light_stat 컬럼 추가
    cursor.execute("DROP TABLE IF EXISTS sensor_data")
    cursor.execute('''
        CREATE TABLE sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            temp REAL,
            humid REAL,
            rain_val INTEGER,
            dist_val INTEGER,
            sound_class TEXT,
            confidence REAL,
            win_stat TEXT,
            heat_stat TEXT,
            light_stat TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print(">>> [온프레미스 서버] DB 초기화 완료 (MQTT 제거됨)")

def save_to_db(data):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sensor_data 
            (timestamp, temp, humid, rain_val, dist_val, sound_class, confidence, win_stat, heat_stat, light_stat)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now(), 
            data.get('temp', 0), data.get('humid', 0), 
            data.get('rain', 1024), data.get('dist', 0), 
            data.get('sound', 'Unknown'), data.get('conf', 0.0),
            data.get('win', 'Unknown'), data.get('heat', 'OFF'), data.get('light', 'OFF')
        ))
        
        conn.commit()
        conn.close()
        # 로그 출력 시 아두이노의 결정을 보여줌
        print(f"[수신] {data.get('sound')} | 창문:{data.get('win')} | 난방:{data.get('heat')}")
        
    except Exception as e:
        print(f"DB 에러: {e}")

# --- 메인 실행 ---
if __name__ == "__main__":
    init_db()
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) 
        print(f">>> 엣지 디바이스 연결 성공: {SERIAL_PORT}")
        
        while True:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    if not line: continue
                    
                    if line.startswith("{") and line.endswith("}"):
                        data = json.loads(line)
                        save_to_db(data)
                except:
                    pass 
            
            time.sleep(0.01)

    except Exception as e:
        print(f"연결 오류: {e}")