import sqlite3
import time
import random
import json
from datetime import datetime

# DB 파일 설정
DB_NAME = "smart_home.db"

def init_db():
    """DB 테이블이 없으면 생성"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            temp REAL,
            humidity REAL,
            trash_type TEXT,
            window_status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_to_db(data):
    """데이터를 DB에 삽입"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sensor_data (timestamp, temp, humidity, trash_type, window_status)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime.now(), data['temp'], data['humidity'], data['trash'], data['window']))
        conn.commit()
        conn.close()
        print(f"[저장 완료] {data}")
    except Exception as e:
        print(f"DB 에러: {e}")

# --- 메인 실행 ---
if __name__ == "__main__":
    init_db()
    print(">>> 백엔드 서버 시작... (가상 데이터 생성 중)")
    
    # [나중에 아두이노 연결 시 사용할 코드]
    # import serial
    # ser = serial.Serial('COM3', 9600) # 포트 번호 확인 필요

    try:
        while True:
            # 1. 실제 환경: 아두이노에서 데이터 읽기
            # if ser.in_waiting > 0:
            #     line = ser.readline().decode('utf-8').strip()
            #     data = json.loads(line) 

            # 2. 테스트 환경: 가상 데이터 생성 (아두이노 없이 테스트)
            dummy_data = {
                "temp": round(random.uniform(20.0, 30.0), 1), # 20~30도 랜덤
                "humidity": round(random.uniform(40.0, 60.0), 1),
                "trash": random.choice(["None", "Can", "Plastic", "None", "None"]), # 가끔 쓰레기 감지
                "window": random.choice(["Open", "Closed"])
            }
            
            # DB 저장
            save_to_db(dummy_data)
            
            # 1초 대기 (아두이노 데이터 전송 주기에 맞춤)
            time.sleep(1)

    except KeyboardInterrupt:
        print("프로그램 종료")