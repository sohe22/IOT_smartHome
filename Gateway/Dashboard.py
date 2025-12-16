import streamlit as st
import sqlite3
import pandas as pd
import time

# --- 페이지 설정 ---
st.set_page_config(
    page_title="스마트홈 관제 시스템",
    page_icon="🏠",
    layout="wide"
)

DB_NAME = "smart_home.db"

# --- CSS 스타일링 (가독성 향상) ---
st.markdown("""
    <style>
    /* 알림 박스 공통 스타일 */
    .alert-box {
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 10px;
        font-weight: bold;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .alert-good { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .alert-rain { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .alert-cold { background-color: #cce5ff; color: #004085; border: 1px solid #b8daff; }
    
    /* 로그 리스트 스타일 */
    .log-container {
        background-color: #ffffff;
        border: 1px solid #e6e6e6;
        border-radius: 8px;
        padding: 10px;
        height: 180px; /* 높이 고정 */
        overflow-y: auto;
    }
    .log-item {
        padding: 8px;
        border-bottom: 1px solid #eee;
        font-size: 14px;
        animation: fadeIn 0.5s;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-5px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* 쓰레기 강조 박스 */
    .trash-box {
        background-color: #fff3cd;
        padding: 20px;
        border-radius: 15px;
        text-align: center;
        border: 2px solid #ffeeba;
        margin-bottom: 15px;
    }
    .trash-icon { font-size: 50px; display: block; margin-bottom: 10px;}
    .trash-text { font-size: 24px; font-weight: bold; color: #856404; }
    </style>
    """, unsafe_allow_html=True)

def get_recent_data(limit=3600):
    """그래프 및 상태 확인용 데이터 (최근 데이터만 로드)"""
    try:
        conn = sqlite3.connect(DB_NAME)
        # 1초에 1개 저장되므로 3600개면 약 1시간 분량
        query = f"SELECT * FROM sensor_data ORDER BY id DESC LIMIT {limit}"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df.sort_values(by='id')
    except:
        return pd.DataFrame()

def get_event_logs(limit=5):
    """오른쪽 로그창용 이벤트 데이터"""
    try:
        conn = sqlite3.connect(DB_NAME)
        # 비(800미만), 차(40미만), 쓰레기(Noise 아님) 인 경우만 필터링
        query = """
            SELECT timestamp, rain_val, dist_val, sound_class 
            FROM sensor_data 
            WHERE rain_val < 800 OR dist_val < 40 OR (sound_class != 'Noise' AND sound_class IS NOT NULL)
            ORDER BY id DESC LIMIT ?
        """
        cursor = conn.execute(query, (limit,))
        logs = cursor.fetchall()
        conn.close()
        return logs
    except:
        return []

def get_latest_trash():
    """가장 최근 버린 쓰레기 조회"""
    try:
        conn = sqlite3.connect(DB_NAME)
        query = "SELECT sound_class, timestamp FROM sensor_data WHERE sound_class != 'Noise' ORDER BY id DESC LIMIT 1"
        cursor = conn.execute(query)
        result = cursor.fetchone()
        conn.close()
        return result if result else ("대기 중", "")
    except:
        return ("대기 중", "")

# --- 헤더 ---
st.title("🏠 AI 스마트홈 모니터링 시스템")
st.markdown("Arduino Nano 33 BLE Sense 기반 엣지 제어 대시보드")
st.divider()

# 메인 컨테이너 (화면 깜빡임 방지용)
main_container = st.empty()

while True:
    with main_container.container():
        # 1. 데이터 로드 (최근 30분 = 1800개)
        df = get_recent_data(limit=1800)
        
        if not df.empty:
            last = df.iloc[-1]
            
            # ==========================================
            # [섹션 1] 알림 및 로그 (좌우 분할)
            # ==========================================
            col_status, col_log = st.columns([1, 1])
            
            # (좌) 현재 상태 카드 (고정)
            with col_status:
                st.subheader("📢 현재 상태 모니터링")
                
                # 상태 판단 로직
                if last['rain_val'] < 800:
                    st.markdown("""
                        <div class="alert-box alert-rain">
                            ☔ <b>[경고] 비 감지됨!</b><br>
                            안전을 위해 창문이 자동으로 닫혔습니다.
                        </div>
                    """, unsafe_allow_html=True)
                elif last['temp'] < 18.0:
                    st.markdown(f"""
                        <div class="alert-box alert-cold">
                            ❄️ <b>[추움] 실내 온도 낮음 ({last['temp']}°C)</b><br>
                            난방 시스템이 가동 중입니다.
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                        <div class="alert-box alert-good">
                            ✅ <b>쾌적함</b><br>
                            현재 날씨와 실내 환경이 좋습니다.<br>
                            (창문 환기 모드 작동 중)
                        </div>
                    """, unsafe_allow_html=True)

            # (우) 실시간 이벤트 로그 (최신 5개 리스트)
            with col_log:
                st.subheader("🔔 실시간 감지 로그")
                logs = get_event_logs(limit=5)
                
                log_html = '<div class="log-container">'
                if logs:
                    for ts, rain, dist, sound in logs:
                        # 시간 포맷 (시:분:초)
                        time_str = pd.to_datetime(ts).strftime("%H:%M:%S")
                        
                        # 메시지 생성
                        if rain < 800:
                            msg = f"☔ 비 감지됨 (센서값: {rain})"
                        elif dist < 40:
                            msg = f"🚗 차량 진입 감지 (거리: {dist}cm)"
                        else:
                            msg = f"🗑️ 쓰레기 분류됨: <b>{sound}</b>"
                        
                        log_html += f'<div class="log-item"><span style="color:#666; margin-right:8px;">[{time_str}]</span>{msg}</div>'
                else:
                    log_html += '<div class="log-item" style="color:#999; text-align:center;">아직 감지된 특이사항이 없습니다.</div>'
                log_html += '</div>'
                
                st.markdown(log_html, unsafe_allow_html=True)

            st.divider()

            # ==========================================
            # [섹션 2] 쓰레기 정보 & 센서 현황
            # ==========================================
            col_trash, col_env = st.columns([1, 2])

            # (좌) 쓰레기 전용 구역
            with col_trash:
                st.subheader("♻️ 최신 수거")
                latest_trash, trash_time = get_latest_trash()
                
                # 아이콘 매핑
                t_icon = "⏳"
                if latest_trash == 'Can': t_icon = "🥫"
                elif latest_trash == 'Plastic': t_icon = "🥤"
                
                # 시간 포맷
                t_time_str = "-"
                if trash_time:
                    t_time_str = pd.to_datetime(trash_time).strftime("%H:%M:%S")

                st.markdown(f"""
                    <div class="trash-box">
                        <span class="trash-icon">{t_icon}</span>
                        <div class="trash-text">{latest_trash}</div>
                        <div style="color:gray; font-size:14px; margin-top:5px;">감지 시간: {t_time_str}</div>
                    </div>
                """, unsafe_allow_html=True)
                
                # 전체 누적 통계
                total_can = df[df['sound_class']=='Can'].shape[0]
                total_plastic = df[df['sound_class']=='Plastic'].shape[0]
                st.caption(f"📊 현재 세션 누적: 캔 {total_can} / 플라스틱 {total_plastic}")

            # (우) 환경 센서 메트릭
            with col_env:
                st.subheader("🌡️ 환경 센서 대시보드")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("온도", f"{last['temp']} °C")
                m2.metric("습도", f"{last['humid']} %")
                m3.metric("빗물 센서", f"{last['rain_val']}")
                
                car_status = "진입함" if last['dist_val'] < 40 else "없음"
                m4.metric("차고 상태", car_status, f"{last['dist_val']}cm")

            # ==========================================
            # [섹션 3] 그래프 (최근 데이터만 표시)
            # ==========================================
            st.subheader(f"📉 온습도 변화 (최근 {len(df)}건)")
            # 차트용 데이터 가공
            chart_data = df[['timestamp', 'temp', 'humid']].copy()
            chart_data['timestamp'] = pd.to_datetime(chart_data['timestamp'])
            chart_data = chart_data.set_index('timestamp')
            
            st.line_chart(chart_data, height=250)

        else:
            st.warning("데이터베이스에 데이터가 없습니다. Backend 서버를 실행해주세요.")

    # 1초 대기 (새로고침)
    time.sleep(1)