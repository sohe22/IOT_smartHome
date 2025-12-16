import serial
import sqlite3
import json
import time
from datetime import datetime

# ===============================================================
# [설정] 환경에 맞게 수정하세요
# ===============================================================
SERIAL_PORT = 'COM3'   # 윈도우: 'COM3', 맥: '/dev/tty.usbmodem...'
BAUD_RATE = 115200     # 아두이노와 동일 필수
DB_NAME = "smart_home.db"
# ===============================================================

# 전역 변수: 아두이노의 마지막 상태 기억 (중복 전송 방지용)
last_sent_command = {}
last_arduino_alert = 0 # 아두이노가 알고 있는 경고 상태

def init_db():
    """DB 초기화"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. 센서 데이터 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            temp REAL, humid REAL, rain_val INTEGER,
            sound_class TEXT, confidence REAL,
            win_stat TEXT, heat_stat TEXT, cool_stat TEXT,
            reason TEXT 
        )
    ''')
    
    # 2. 시스템 제어 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_control (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mode TEXT DEFAULT 'AUTO',
            cmd_win TEXT DEFAULT 'Open',
            cmd_heat TEXT DEFAULT 'OFF',
            cmd_cool TEXT DEFAULT 'OFF',
            manual_expiry TEXT,
            trash_alert INTEGER DEFAULT 0
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO system_control (id, mode, cmd_win, cmd_heat, cmd_cool, trash_alert) VALUES (1, 'AUTO', 'Open', 'OFF', 'OFF', 0)")
    
    conn.commit()
    conn.close()
    print(">>> [게이트웨이] DB 연결 및 초기화 완료")

def get_control_state():
    """DB에서 사용자 명령 읽기"""
    try:
        conn = sqlite3.connect(DB_NAME)
        row = conn.execute("SELECT mode, cmd_win, cmd_heat, cmd_cool, manual_expiry, trash_alert FROM system_control WHERE id=1").fetchone()
        conn.close()
        return row if row else ('AUTO', 'Open', 'OFF', 'OFF', None, 0)
    except:
        return ('AUTO', 'Open', 'OFF', 'OFF', None, 0)

def update_db_from_arduino(data):
    """아두이노 데이터 DB 저장"""
    global last_arduino_alert
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. 센서 데이터 저장
        cursor.execute('''
            INSERT INTO sensor_data 
            (timestamp, temp, humid, rain_val, sound_class, confidence, win_stat, heat_stat, cool_stat, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now(), 
            data.get('temp', 0), data.get('humid', 0), data.get('rain', 0),
            data.get('sound', 'Unknown'), data.get('conf', 0),
            data.get('win_stat', 'Unknown'), data.get('heat_stat', 'OFF'), data.get('cool_stat', 'OFF'),
            data.get('reason', '')
        ))
        
        # 2. 아두이노 경고 상태 동기화
        # 아두이노가 "경고(1)"를 보냈다면 DB도 "경고(1)"로 만듦
        arduino_alert = data.get('trash_alert', 0)
        last_arduino_alert = arduino_alert # 상태 기억
        
        if arduino_alert == 1:
            cursor.execute("UPDATE system_control SET trash_alert=1 WHERE id=1")
        
        conn.commit()
        conn.close()
        
        # 센서 값 디버깅을 위해 상세 출력
        t = data.get('temp')
        h = data.get('humid')
        r = data.get('rain')
        sound = data.get('sound')
        reason = data.get('reason')
        
        # 보기 좋게 포맷팅
        print(f"[수신] T:{t}°C H:{h}% Rain:{r} | 소리:{sound} | {reason}")
        
    except Exception as e:
        print(f"DB Save Error: {e}")

def check_timer_and_update_db(mode, expiry_str):
    """타이머 만료 체크"""
    if mode == 'MANUAL' and expiry_str:
        try:
            expiry_time = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S.%f")
            if datetime.now() > expiry_time:
                print(">>> [Timer] 시간 종료 -> AUTO 복귀")
                conn = sqlite3.connect(DB_NAME)
                conn.execute("UPDATE system_control SET mode='AUTO' WHERE id=1")
                conn.commit()
                conn.close()
                return 'AUTO'
        except:
            pass
    return mode

# ===============================================================
# 메인 루프
# ===============================================================
if __name__ == "__main__":
    init_db()
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) # 리셋 대기
        print(f">>> 아두이노 연결 성공 ({SERIAL_PORT})")
    except Exception as e:
        print(f"!!! 연결 실패: {e}")
        exit()

    try:
        while True:
            # -----------------------------------------------------
            # [1] 아두이노 -> PC (수신)
            # -----------------------------------------------------
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    if line.startswith("{") and line.endswith("}"):
                        edge_data = json.loads(line)
                        update_db_from_arduino(edge_data)
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    print(f"Read Error: {e}")

            # -----------------------------------------------------
            # [2] PC -> 아두이노 (송신)
            # -----------------------------------------------------
            db_mode, db_win, db_heat, db_cool, expiry, db_alert = get_control_state()
            
            # 타이머 체크
            current_mode = check_timer_and_update_db(db_mode, expiry)
            
            # 보낼 명령 구성
            command = {
                "mode": current_mode,
                "win": db_win,
                "heat": db_heat,
                "cool": db_cool
            }
            
            # [중요] 경고 해제 로직 개선
            # 아두이노는 경고중(1)인데, DB는 해결됨(0)일 때만 해제 명령 전송
            if last_arduino_alert == 1 and db_alert == 0:
                command["resolve"] = "Resolved"
                # 해제 명령은 즉시 보내야 하므로 강제 전송
                last_sent_command = {} 

            # [최적화] 변경사항이 있을 때만 전송 (트래픽 감소)
            # 단, resolve 명령이 있거나 2초마다 한 번은 Alive 신호 겸 전송
            # current_time = time.time()
            # last_sent_time 등을 활용해도 되지만, 간단히 내용 비교
            
            if command != last_sent_command or "resolve" in command:
                msg = json.dumps(command) + "\n"
                ser.write(msg.encode('utf-8'))
                print(f"[전송] {msg.strip()}")
                last_sent_command = command
            
            # 너무 빠른 루프 방지
            time.sleep(0.1) 

    except KeyboardInterrupt:
        print("\n종료")
        ser.close()