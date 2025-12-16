import streamlit as st
import sqlite3
import pandas as pd
import time
import streamlit.components.v1 as components 
from datetime import datetime, timedelta

# --- 페이지 설정 ---
st.set_page_config(page_title="스마트홈 관제 시스템", page_icon="🏠", layout="wide")
DB_NAME = "smart_home.db"

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .trash-panel { 
        background-color: #fff3e0; padding: 20px; border-radius: 15px; 
        border: 2px solid #ffe0b2; text-align: center; margin-bottom: 20px;
    }
    .trash-title { font-size: 20px; font-weight: bold; color: #e65100; }
    .trash-icon { font-size: 60px; display: block; margin: 10px 0; }
    .stat-box {
        background-color: #e3f2fd; padding: 15px; border-radius: 10px;
        text-align: center; border: 1px solid #bbdefb;
    }
    .control-card { 
        background-color: #ffffff; padding: 20px; border-radius: 12px; 
        border: 1px solid #e0e0e0; height: 100%; text-align: center;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .status-badge {
        font-size: 24px; font-weight: 800; padding: 10px 20px;
        border-radius: 8px; display: inline-block; margin: 15px 0;
        width: 100%; text-align: center; color: white;
    }
    .bg-green { background-color: #28a745; }
    .bg-gray { background-color: #6c757d; }
    .bg-red { background-color: #dc3545; }
    .bg-blue { background-color: #007bff; }
    .notification-box {
        background-color: #2b313e; color: #ffffff; padding: 15px;
        border-radius: 10px; font-family: 'Consolas', monospace;
        margin-bottom: 20px; border: 1px solid #4a5060;
    }
    .noti-header-auto { color: #4caf50; font-weight: bold; font-size: 16px; margin-bottom: 10px; }
    .noti-header-manual { color: #ff9800; font-weight: bold; font-size: 16px; margin-bottom: 10px; }
    .log-item { font-size: 14px; margin-bottom: 5px; border-bottom: 1px dashed #555; padding: 5px; }
    .log-ignored { color: #999; font-style: italic; }
    .latest-log {
        background-color: #3e4451;
        border-left: 5px solid #ffeb3b;
        color: #ffeb3b; font-weight: bold;
        animation: flash 2s infinite;
    }
    </style>
""", unsafe_allow_html=True)

# --- DB 함수들 ---
def get_system_status():
    try:
        conn = sqlite3.connect(DB_NAME)
        row = conn.execute("SELECT mode, cmd_win, cmd_heat, cmd_cool, trash_alert FROM system_control WHERE id=1").fetchone()
        conn.close()
        return row if row else ('AUTO', 'Open', 'OFF', 'OFF', 0)
    except:
        return ('AUTO', 'Open', 'OFF', 'OFF', 0)

def set_manual_control(target, action, duration_str):
    seconds = 5
    if duration_str == "1분": seconds = 60
    elif duration_str == "10분": seconds = 600
    expiry_time = datetime.now() + timedelta(seconds=seconds)
    
    conn = sqlite3.connect(DB_NAME)
    if target == 'window':
        conn.execute("UPDATE system_control SET mode='MANUAL', cmd_win=?, manual_expiry=? WHERE id=1", (action, str(expiry_time)))
    elif target == 'heat':
        other_cool = "OFF" if action == "ON" else "OFF"
        conn.execute("UPDATE system_control SET mode='MANUAL', cmd_heat=?, cmd_cool=?, manual_expiry=? WHERE id=1", (action, other_cool, str(expiry_time)))
    elif target == 'cool':
        other_heat = "OFF" if action == "ON" else "OFF"
        conn.execute("UPDATE system_control SET mode='MANUAL', cmd_cool=?, cmd_heat=?, manual_expiry=? WHERE id=1", (action, other_heat, str(expiry_time)))
    conn.commit()
    conn.close()

def resolve_trash_error(decision):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE system_control SET trash_alert=0 WHERE id=1")
    conn.execute("""
        INSERT INTO sensor_data (timestamp, sound_class, confidence, win_stat, heat_stat, cool_stat, reason)
        VALUES (?, ?, 1.0, 'Maintain', 'Maintain', 'Maintain', '사용자 수동 분류')
    """, (datetime.now(), decision))
    conn.commit()
    conn.close()
    st.toast(f"✅ '{decision}'(으)로 분류 확정!", icon="👍")

def get_latest_data(limit=300):
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query(f"SELECT * FROM sensor_data ORDER BY id DESC LIMIT {limit}", conn)
        conn.close()
        return df.sort_values(by='id')
    except:
        return pd.DataFrame()

def get_trash_stats():
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT sound_class FROM sensor_data WHERE sound_class IN ('Can', 'Plastic')", conn)
        conn.close()
        return df[df['sound_class'] == 'Can'].shape[0], df[df['sound_class'] == 'Plastic'].shape[0]
    except:
        return 0, 0

# --- 상태 관리 ---
if 'control_step' not in st.session_state: st.session_state['control_step'] = None
if 'pending_action' not in st.session_state: st.session_state['pending_action'] = None
if 'pending_target' not in st.session_state: st.session_state['pending_target'] = None

# --- 메인 로직 ---
df = get_latest_data()
cur_mode, cur_win, cur_heat, cur_cool, trash_alert = get_system_status()
can_cnt, plastic_cnt = get_trash_stats()

st.title("🏠 지능형 스마트홈 대시보드")
st.divider()

if not df.empty:
    last = df.iloc[-1]
    
    # [기능] 분류 불확실 시 맨 위로 스크롤
    if trash_alert == 1:
        components.html("""<script>window.scrollTo({top: 0, behavior: 'smooth'});</script>""", height=0, width=0)

    # [섹션 1] 쓰레기 분류 & 통계
    col_stat1, col_stat2 = st.columns([1, 2])
    
    with col_stat1:
        st.subheader("📊 수거 통계")
        st.markdown(f"""
            <div class="stat-box">
                <h3>🥫 캔: {can_cnt}개</h3>
                <h3>🥤 플라스틱: {plastic_cnt}개</h3>
                <hr>
                <b>총합: {can_cnt + plastic_cnt}개</b>
            </div>
        """, unsafe_allow_html=True)
        
    with col_stat2:
        st.subheader("♻️ 실시간 분류 현황")
        alert_placeholder = st.empty()
        
        if trash_alert == 1:
            with alert_placeholder.container():
                st.error("⚠️ **[경고] AI 분류 실패! 쓰레기를 선택해주세요.**", icon="🚨")
                c1, c2 = st.columns(2)
                if c1.button("🥫 캔", type="primary", use_container_width=True, key="res_can"):
                    resolve_trash_error("Can")
                    time.sleep(0.1)
                    st.rerun()
                if c2.button("🥤 플라스틱", type="primary", use_container_width=True, key="res_plastic"):
                    resolve_trash_error("Plastic")
                    time.sleep(0.1)
                    st.rerun()
        else:
            trash_logs = df[df['sound_class'].isin(['Can', 'Plastic'])]
            if not trash_logs.empty:
                recent = trash_logs.iloc[-1]
                r_name = recent['sound_class']
                r_time = pd.to_datetime(recent['timestamp']).strftime("%H:%M:%S")
                icon = "🥫" if r_name == 'Can' else "🥤"
                msg = f"{r_time}에 수거됨"
            else:
                icon = "⏳"
                r_name = "대기 중"
                msg = "아직 수거된 쓰레기가 없습니다."
            st.markdown(f"""<div class="trash-panel"><span class="trash-icon">{icon}</span><div style="font-size: 24px; font-weight:bold;">{r_name}</div><div style="color:gray;">{msg}</div></div>""", unsafe_allow_html=True)

    st.divider()

    # [섹션 2] 통합 제어 센터
    st.subheader("🎮 통합 제어 센터")

    # (A) 알림 센터
    log_df = df[['reason']].tail(3).iloc[::-1].reset_index(drop=True)
    mode_text = "🟢 자동 제어 모드 (Auto Mode)" if cur_mode == 'AUTO' else "🟠 사용자 제어 모드 (Manual Control)"
    mode_class = "noti-header-auto" if cur_mode == 'AUTO' else "noti-header-manual"
    
    log_html = f'<div class="notification-box"><div class="{mode_class}">{mode_text}</div>'
    for idx, row in log_df.iterrows():
        reason_txt = row['reason']
        item_class = "log-item latest-log" if idx == 0 else "log-item"
        if cur_mode == 'MANUAL':
            log_html += f'<div class="{item_class} log-ignored">(무시됨) {reason_txt}</div>'
        else:
            prefix = "⚡ 최신 판단: " if idx == 0 else "▶ "
            log_html += f'<div class="{item_class}">{prefix}{reason_txt}</div>'
    log_html += "</div>"
    st.markdown(log_html, unsafe_allow_html=True)

    # (B) 제어 패널
    c_win, c_temp = st.columns([1, 2])

    with c_win:
        st.markdown('<div class="control-card"><h4>🪟 창문 제어</h4>', unsafe_allow_html=True)
        actual_win = last['win_stat']
        if "Open" in actual_win:
            win_bg = "bg-green"; display_win = "OPEN"; target_action = "Closed"
        else:
            win_bg = "bg-gray"; display_win = "CLOSED"; target_action = "Open"
            
        st.markdown(f'<div class="status-badge {win_bg}">{display_win}</div>', unsafe_allow_html=True)
        
        if st.session_state['control_step'] != 'window_timer':
            if st.button(target_action, key="btn_win_toggle", use_container_width=True):
                st.session_state['control_step'] = 'window_timer'
                st.session_state['pending_target'] = 'window'
                st.session_state['pending_action'] = target_action
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with c_temp:
        st.markdown('<div class="control-card"><h4>🌡️ 실내 온도 제어</h4>', unsafe_allow_html=True)
        sub_c1, sub_c2 = st.columns(2)
        
        # [수정] 조명(Light) 대신 난방/냉방 상태 표시
        with sub_c1:
            actual_heat = last['heat_stat']
            if "ON" in actual_heat:
                heat_bg = "bg-red"; display_heat = "ON"; target_heat = "OFF"
            else:
                heat_bg = "bg-gray"; display_heat = "OFF"; target_heat = "ON"
            st.markdown(f'<div class="status-badge {heat_bg}">🔥 난방 {display_heat}</div>', unsafe_allow_html=True)
            if st.session_state['control_step'] == None:
                if st.button(target_heat, key="btn_heat_toggle", use_container_width=True):
                    st.session_state['control_step'] = 'heat_timer'
                    st.session_state['pending_target'] = 'heat'
                    st.session_state['pending_action'] = target_heat
                    st.rerun()

        with sub_c2:
            actual_cool = last['cool_stat']
            if "ON" in actual_cool:
                cool_bg = "bg-blue"; display_cool = "ON"; target_cool = "OFF"
            else:
                cool_bg = "bg-gray"; display_cool = "OFF"; target_cool = "ON"
            st.markdown(f'<div class="status-badge {cool_bg}">❄️ 냉방 {display_cool}</div>', unsafe_allow_html=True)
            if st.session_state['control_step'] == None:
                if st.button(target_cool, key="btn_cool_toggle", use_container_width=True):
                    st.session_state['control_step'] = 'cool_timer'
                    st.session_state['pending_target'] = 'cool'
                    st.session_state['pending_action'] = target_cool
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state['control_step'] is not None:
        with st.container():
            st.info(f"📢 '{st.session_state['pending_target']}'을(를) '{st.session_state['pending_action']}' 상태로 변경합니다.")
            sel_duration = st.selectbox("유지 시간 선택", ["5초", "1분", "10분"], key="univ_dur")
            col_y, col_n = st.columns(2)
            if col_y.button("확인 (전송)", key="univ_confirm", type="primary"):
                set_manual_control(st.session_state['pending_target'], st.session_state['pending_action'], sel_duration)
                st.toast("✅ 제어 명령 전송 완료!", icon="📡")
                st.session_state['control_step'] = None
                st.rerun()
            if col_n.button("취소", key="univ_cancel"):
                st.session_state['control_step'] = None
                st.rerun()

    st.divider()

    # [섹션 3] 센서 그래프
    st.subheader("📈 실시간 환경 센서")
    col_chart1, col_chart2 = st.columns(2)
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    chart_data1 = df[['timestamp', 'temp', 'humid']].set_index('timestamp')
    chart_data2 = df[['timestamp', 'rain_val']].set_index('timestamp')
    
    with col_chart1:
        st.caption("온도(Red) / 습도(Blue)")
        st.line_chart(chart_data1, height=250, color=["#FF0000", "#0000FF"])
    with col_chart2:
        st.caption("빗물 센서 값")
        st.line_chart(chart_data2, height=250)

else:
    st.warning("데이터 연결 대기 중... Backend 서버를 실행해주세요.")

time.sleep(1)
st.rerun()