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

# --- CSS 스타일링 ---
st.markdown("""
    <style>
    /* 알림 박스 스타일 */
    .alert-box {
        padding: 15px; border-radius: 10px; margin-bottom: 10px;
        font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .alert-rain { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .alert-cold { background-color: #cce5ff; color: #004085; border: 1px solid #b8daff; }
    .alert-good { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    
    /* 카드 스타일 */
    .stat-card {
        background-color: #f9f9f9; padding: 15px; border-radius: 8px;
        border: 1px solid #ddd; text-align: center;
    }
    
    /* 로그 스타일 */
    .log-container {
        background-color: #ffffff; border: 1px solid #e6e6e6;
        border-radius: 8px; padding: 10px; height: 200px; overflow-y: auto;
    }
    .log-item { padding: 5px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
    </style>
    """, unsafe_allow_html=True)

def get_recent_data(limit=1800):
    try:
        conn = sqlite3.connect(DB_NAME)
        # 모든 컬럼(*)을 가져오므로 win_stat, heat_stat 등이 포함됨
        df = pd.read_sql_query(f"SELECT * FROM sensor_data ORDER BY id DESC LIMIT {limit}", conn)
        conn.close()
        return df.sort_values(by='id')
    except:
        return pd.DataFrame()

def get_latest_trash():
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
st.title("🏠 온프레미스 Edge 관제 시스템")
st.markdown("모든 제어 판단은 **Arduino Nano 33 BLE Sense** 내부에서 수행됩니다.")
st.divider()

# 메인 컨테이너
main_container = st.empty()

while True:
    with main_container.container():
        df = get_recent_data()
        
        if not df.empty:
            last = df.iloc[-1]
            
            # [섹션 1] 엣지 디바이스 상태 리포트 (Alert Area)
            # 서버가 판단하는 게 아니라, 아두이노가 보낸 'win_stat'을 그대로 보여줌
            current_win_stat = last['win_stat']
            
            if "Rain" in current_win_stat:
                st.markdown(f"""
                    <div class="alert-box alert-rain">
                        ☔ <b>[Edge Report] 비 감지 대응</b><br>
                        디바이스가 창문을 닫았습니다. (Status: {current_win_stat})
                    </div>
                """, unsafe_allow_html=True)
            elif "Cold" in current_win_stat:
                st.markdown(f"""
                    <div class="alert-box alert-cold">
                        ❄️ <b>[Edge Report] 저온 대응</b><br>
                        디바이스가 난방을 켜고 창문을 닫았습니다. (Status: {current_win_stat})
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div class="alert-box alert-good">
                        ✅ <b>[Edge Report] 정상 상태</b><br>
                        디바이스가 환기 모드를 유지 중입니다. (Status: Open)
                    </div>
                """, unsafe_allow_html=True)

            # [섹션 2] 핵심 상태 지표 (Metrics)
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("🌡️ 실내 온도", f"{last['temp']} °C", f"난방 {last['heat_stat']}")
            
            with col2:
                # 아두이노가 보낸 상태값을 보여줌
                is_on = (last['light_stat'] == "ON")
                st.metric("🚗 차고 조명", last['light_stat'], "차량 감지됨" if is_on else "대기 중")
            
            with col3:
                st.metric("☔ 빗물 센서값", last['rain_val'], "창문 " + last['win_stat'])
            
            with col4:
                st.metric("🔊 소리 AI 분석", last['sound_class'], f"신뢰도 {last['confidence']*100:.0f}%")

            # [섹션 3] 쓰레기 & 차트 & 로그
            col_chart, col_log = st.columns([2, 1])
            
            with col_chart:
                st.subheader("📈 온습도 변화 추이")
                chart_data = df[['timestamp', 'temp', 'humid']].set_index('timestamp')
                st.line_chart(chart_data, height=250)

                # 쓰레기 정보 하단 표시
                latest_trash, t_time = get_latest_trash()
                if t_time:
                    t_time = pd.to_datetime(t_time).strftime("%H:%M:%S")
                st.info(f"♻️ **최근 수거된 쓰레기:** {latest_trash} ({t_time})")

            with col_log:
                st.subheader("📋 디바이스 결정 로그")
                # 판단 결과(win_stat, light_stat 등)가 변한 기록만 보여주면 좋겠지만,
                # 여기서는 최근 로그를 보여주되 '상태' 컬럼을 강조
                log_df = df[['timestamp', 'win_stat', 'light_stat', 'sound_class']].sort_values(by='timestamp', ascending=False).head(10)
                st.dataframe(log_df, hide_index=True, use_container_width=True)
        
        else:
            st.warning("데이터가 없습니다. Simulated_Backend.py를 실행해주세요.")

    time.sleep(1)