import sqlite3
import time
import random
from datetime import datetime

# --- 설정 ---
DB_NAME = "smart_home.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 테이블이 꼬이지 않게 기존 테이블 삭제 후 재생성
    cursor.execute("DROP TABLE IF EXISTS sensor_data")
    cursor.execute('''
        CREATE TABLE sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            temp REAL,
            humid REAL,  -- 여기를 'humid'로 통일
            rain_val INTEGER,
            dist_val INTEGER,
            sound_class TEXT,
            confidence REAL
        )
    ''')
    conn.commit()
    conn.close()
    print(">>> [가상 서버] DB 초기화 완료 (Schema: temp, humid, rain...)")

def generate_dummy_data():
    """가상 데이터 생성 시나리오"""
    
    # 기본 환경
    temp = round(random.uniform(18.0, 26.0), 1)
    humid = round(random.uniform(40.0, 60.0), 1)
    
    # 시나리오 1: 비가 오는 상황 (20% 확률)
    if random.random() < 0.2:
        rain_val = random.randint(0, 700) # 800 미만이면 비
        temp -= 2.0 
    else:
        rain_val = random.randint(900, 1024) 

    # 시나리오 2: 차가 들어온 상황 (10% 확률)
    if random.random() < 0.1:
        dist_val = random.randint(5, 30) # 40cm 미만
    else:
        dist_val = random.randint(100, 200)

    # 시나리오 3: 쓰레기 감지
    rand_sound = random.random()
    if rand_sound < 0.1:
        sound_class = "Can"
        confidence = round(random.uniform(0.85, 0.99), 2)
    elif rand_sound < 0.2:
        sound_class = "Plastic"
        confidence = round(random.uniform(0.80, 0.95), 2)
    else:
        sound_class = "Noise"
        confidence = round(random.uniform(0.5, 0.99), 2)

    return {
        'temp': temp, 'humid': humid, 'rain': rain_val,
        'dist': dist_val, 'sound': sound_class, 'conf': confidence
    }

def save_to_db(data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sensor_data 
        (timestamp, temp, humid, rain_val, dist_val, sound_class, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now(), data['temp'], data['humid'], 
        data['rain'], data['dist'], data['sound'], data['conf']
    ))
    conn.commit()
    conn.close()
    print(f"[생성] {data['sound']} | 온습도: {data['temp']}/{data['humid']} | 비: {data['rain']}")

if __name__ == "__main__":
    init_db()
    print(">>> [시뮬레이터] 가동 시작...")
    try:
        while True:
            dummy = generate_dummy_data()
            save_to_db(dummy)
            time.sleep(1) 
    except KeyboardInterrupt:
        print("\n종료")