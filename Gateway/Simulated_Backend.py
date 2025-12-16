import sqlite3
import time
import random
from datetime import datetime

# --- 설정 ---
DB_NAME = "smart_home.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS sensor_data")
    # [변경] 아두이노의 판단 결과(win_stat, heat_stat, light_stat) 컬럼 추가
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
    print(">>> [가상 엣지 시뮬레이터] DB 초기화 완료 (Schema Updated)")

def generate_edge_data():
    """아두이노 펌웨어 로직을 100% 모방하여 데이터 생성"""
    
    # 1. 센서 데이터 랜덤 생성
    temp = round(random.uniform(15.0, 26.0), 1) # 18도 미만 테스트를 위해 범위 조정
    humid = round(random.uniform(40.0, 60.0), 1)
    
    # 비 시나리오 (20% 확률)
    if random.random() < 0.2:
        rain_val = random.randint(0, 700) 
    else:
        rain_val = random.randint(900, 1024) 

    # 차 시나리오 (10% 확률)
    if random.random() < 0.1:
        dist_val = random.randint(5, 30) 
    else:
        dist_val = random.randint(100, 200)

    # 소리 시나리오
    rand_sound = random.random()
    if rand_sound < 0.1:
        sound_class = "Can"
        conf = round(random.uniform(0.85, 0.99), 2)
    elif rand_sound < 0.2:
        sound_class = "Plastic"
        conf = round(random.uniform(0.80, 0.95), 2)
    else:
        sound_class = "Noise"
        conf = round(random.uniform(0.5, 0.99), 2)

    # ---------------------------------------------------------
    # [Edge Logic Simulation] 아두이노가 수행할 판단을 여기서 미리 계산
    # ---------------------------------------------------------
    win_stat = "Open"
    heat_stat = "OFF"
    light_stat = "OFF"

    # 로직 1: 창문 & 난방
    is_raining = (rain_val < 800)
    
    if is_raining or temp < 18.0:
        if is_raining: win_stat = "Closed(Rain)"
        else: win_stat = "Closed(Cold)"
        
        if temp < 18.0: heat_stat = "ON"
        else: heat_stat = "OFF"
    else:
        win_stat = "Open"
        heat_stat = "OFF"

    # 로직 2: 조명
    if 0 < dist_val < 40:
        light_stat = "ON"
    else:
        light_stat = "OFF"

    return {
        'temp': temp, 'humid': humid, 'rain': rain_val,
        'dist': dist_val, 'sound': sound_class, 'conf': conf,
        'win': win_stat, 'heat': heat_stat, 'light': light_stat
    }

def save_to_db(data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sensor_data 
        (timestamp, temp, humid, rain_val, dist_val, sound_class, confidence, win_stat, heat_stat, light_stat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now(), 
        data['temp'], data['humid'], data['rain'], data['dist'], 
        data['sound'], data['conf'], 
        data['win'], data['heat'], data['light']
    ))
    conn.commit()
    conn.close()
    print(f"[Edge Report] {data['sound']} | Win:{data['win']} | Heat:{data['heat']} | Light:{data['light']}")

if __name__ == "__main__":
    init_db()
    print(">>> [시뮬레이터] 아두이노의 판단 로직을 시뮬레이션합니다...")
    try:
        while True:
            dummy = generate_edge_data()
            save_to_db(dummy)
            time.sleep(1) 
    except KeyboardInterrupt:
        print("\n종료")