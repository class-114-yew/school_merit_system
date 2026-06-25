import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import pandas as pd
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from PIL import Image
import io
import base64

# ==========================================
# ⚙️ 系統發信伺服器設定 (請在此輸入你的設定)
# ==========================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "yew@wces.tc.edu.tw"       # 更改為你的 Gmail 帳號
SMTP_PASSWORD = "msye vyun ygqy wwij"           # 更改為你的 16 位應用程式密碼

# ==========================================
# 1. 初始化 Firebase
# ==========================================
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        # 改從 Streamlit 雲端安全後台讀取憑證，不依賴本機 json 檔案
        firebase_creds = dict(st.secrets["firebase_credentials"])
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()

st.set_page_config(page_title="校內榮譽積點系統", page_icon="🏅", layout="wide")
st.markdown(
    """
    <script>
        document.documentElement.lang = 'zh-TW';
    </script>
    """,
    unsafe_allow_html=True
)

# ==========================================
# 2. 🚀 高性能定向快取區
# ==========================================

@st.cache_data(ttl=600)  
def verify_session_token(username, session_token):
    """驗證安全 Token，高頻重整網頁時直接走快取，完全不消耗 Firebase 讀取額度"""
    user_doc = db.collection("users").document(username).get()
    if user_doc.exists:
        u_data = user_doc.to_dict()
        # 確保帳號未被停用，且資料庫中的 token 與網址完全一致
        if u_data.get("status") != "disabled" and u_data.get("session_token") == session_token:
            return u_data
    return None

@st.cache_data(ttl=600)  
def get_cached_ocean_stages():
    """從 Firebase 撈取晉級階段設定，若無則自動初始化預設值"""
    doc = db.collection("system_settings").document("ocean_stages").get()
    if doc.exists:
        return doc.to_dict().get("stages", [])
    else:
        # 初始化預設值
        default_stages = [
            {"points": 1500, "stage": "終極榮譽頂峰", "avatar": "🏆", "reward": "七級文昌之星榮譽獎牌"},
            {"points": 1350, "stage": "👑 菁英海洋階段", "avatar": "👑", "reward": "六級徽章"},
            {"points": 1250, "stage": "👑 菁英海洋階段", "avatar": "👑", "reward": "校長室下午茶點心"},
            {"points": 1150, "stage": "👑 菁英海洋階段", "avatar": "👑", "reward": "六級獎狀 1 張"},
            {"points": 1050, "stage": "🦑 深海探險階段", "avatar": "🦑", "reward": "五級榮譽徽章"},
            {"points": 960,  "stage": "🦑 深海探險階段", "avatar": "🦑", "reward": "五級獎狀 1 張"},
            {"points": 870,  "stage": "🦑 深海探險階段", "avatar": "🦑", "reward": "兌換券"},
            {"points": 780,  "stage": "🐋 大洋探險階段", "avatar": "🐋", "reward": "四級榮譽徽章"},
            {"points": 700,  "stage": "🐋 大洋探險階段", "avatar": "🐋", "reward": "四級獎狀 1 張"},
            {"points": 620,  "stage": "🐋 大洋探險階段", "avatar": "🐋", "reward": "兌換券"},
            {"points": 540,  "stage": "🦈 高級海洋階段", "avatar": "🦈", "reward": "三級榮譽徽章"},
            {"points": 470,  "stage": "🦈 高級海洋階段", "avatar": "🦈", "reward": "三級獎狀 1 張"},
            {"points": 400,  "stage": "🦈 高級海洋階段", "avatar": "🦈", "reward": "兌換券"},
            {"points": 330,  "stage": "🐠 中級海洋階段", "avatar": "🐠", "reward": "二級榮譽徽章"},
            {"points": 270,  "stage": "🐠 中級海洋階段", "avatar": "🐠", "reward": "二級獎狀 1 張"},
            {"points": 210,  "stage": "🐠 中級海洋階段", "avatar": "🐠", "reward": "兌換券 1 張"},
            {"points": 150,  "stage": "🐟 初級海洋階段", "avatar": "🐟", "reward": "一級榮譽徽章"},
            {"points": 100,  "stage": "🐟 初級海洋階段", "avatar": "🐟", "reward": "一級獎狀 1 張"},
            {"points": 50,   "stage": "🐟 初級海洋階段", "avatar": "🐟", "reward": "兌換券 1 張"}
        ]
        db.collection("system_settings").document("ocean_stages").set({"stages": default_stages})
        return default_stages

def get_student_avatar_and_stage(points, stages_config):
    """計算學生目前對應的頭像、階段名稱與獎勵"""
    for s in sorted(stages_config, key=lambda x: x["points"], reverse=True):
        if points >= s["points"]:
            return s["avatar"], s["stage"], s["reward"]
    return "👶", "潛水初心階段", "無"

@st.cache_data(ttl=3600)  
def get_cached_active_classes():
    all_students = db.collection("users").where("role", "==", "student").where("status", "==", "active").get()
    return sorted(list(set([s.to_dict().get("current_class") for s in all_students if s.to_dict().get("current_class")])))

@st.cache_data(ttl=1800)  
def get_cached_students_by_class(target_class):
    class_students = db.collection("users").where("current_class", "==", target_class).where("status", "==", "active").get()
    stages_config = get_cached_ocean_stages()
    student_list = []
    for s in class_students:
        sd = s.to_dict()
        pts = sd.get("total_points", 0)
        avatar, _, _ = get_student_avatar_and_stage(pts, stages_config)
        
        clean_avatar = "🖼️ 圖標" if "<img" in avatar else avatar
        student_list.append({
            "label": f"{sd.get('current_seat_no')}號 - {clean_avatar} {sd.get('name')} ({pts}點)", 
            "id": sd.get("username"),
            "seat": int(sd.get('current_seat_no', 0))
        })
    student_list.sort(key=lambda x: x["seat"])
    return student_list

@st.cache_data(ttl=300)   
def get_cached_homeroom_report(view_class):
    c_students = db.collection("users").where("current_class", "==", view_class).get()
    stages_config = get_cached_ocean_stages()
    report_data = []
    for s in c_students:
        sd = s.to_dict()
        status_text = "🟢 正常" if sd.get("status", "active") == "active" else "🔴 停用"
        pts = sd.get("total_points", 0)
        avatar, stage_name, _ = get_student_avatar_and_stage(pts, stages_config)
        
        clean_avatar = "🖼️" if "<img" in avatar else avatar
        report_data.append({
            "座號": str(sd.get("current_seat_no", "")),
            "學號": sd.get("username"),
            "姓名": f"{clean_avatar} {sd.get('name')}",
            "目前海洋階段": stage_name,
            "狀態": status_text,
            "總積點數": pts 
        })
    return report_data

@st.cache_data(ttl=120)
def get_cached_student_logs(username):
    logs = db.collection("point_logs").where("student_id", "==", username).limit(300).get()
    data = []
    for log in logs:
        d = log.to_dict()
        ts = d.get("timestamp")
        time_str = ts.strftime("%Y-%m-%d %H:%M") if ts else d.get("date_str")
        data.append({
            "日期": time_str,
            "分類": d.get("category"),
            "點數": d.get("points", 1), 
            "事由/備註": d.get("reason"),
            "給點教師": d.get("teacher_id"),
            "raw_ts": ts if ts else datetime.min
        })
    data.sort(key=lambda x: x["raw_ts"], reverse=True)
    for d in data: d.pop("raw_ts", None)
    return data

@st.cache_data(ttl=120)
def get_cached_teacher_logs(username):
    my_logs = db.collection("point_logs").where("teacher_id", "==", username).limit(300).get()
    history = []
    for l in my_logs:
        ld = l.to_dict()
        history.append({
            "日期": ld.get("date_str"), 
            "學生學號": ld.get("student_id"), 
            "分類": ld.get("category"), 
            "點數": ld.get("points", 1), 
            "事由": ld.get("reason")
        })
    return history

# ==========================================
# 3. 精準快取沖刷控制閥
# ==========================================
def refresh_point_related_caches():
    get_cached_students_by_class.clear() 
    get_cached_homeroom_report.clear()
    get_cached_student_logs.clear()
    get_cached_teacher_logs.clear()

def refresh_all_system_caches():
    get_cached_ocean_stages.clear()
    get_cached_active_classes.clear()
    get_cached_students_by_class.clear()
    get_cached_homeroom_report.clear()
    get_cached_student_logs.clear()
    get_cached_teacher_logs.clear()
    verify_session_token.clear() 

# ==========================================
# 4. 核心功能函式
# ==========================================

def send_verification_email(to_email, code):
    try:
        body = f"您好：\n\n您的校內榮譽積點系統密碼重設驗證碼為：【 {code} 】\n請於網頁中變更您的密碼。"
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "【校內榮譽積點系統】密碼重設驗證碼"
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [to_email], msg.as_string())
        server.quit()
        return True, "驗證碼已成功發送！"
    except Exception as e:
        return False, f"郵件發送失敗: {e}"

def send_report_email_with_csv(to_email, df, report_title):
    try:
        msg = MIMEMultipart()
        msg["Subject"] = f"🏅【校內榮譽積點系統】{report_title}"
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        
        body = f"您好：\n\n這是系統為您自動核算並導出的「{report_title}」。\n全校目前已達榮譽階級門檻之學生名單詳見附件 CSV 檔案。\n\n提示：附件已採用內置 UTF-8-BOM 編碼，您可直接使用 Excel 雙擊開啟，絕不卡中文亂碼。\n\n系統自動發送信件 - 請勿直接回覆"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        csv_data = df.to_csv(index=False).encode('utf-8-sig')
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(csv_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="Honor_Milestone_Report_{datetime.now().strftime("%Y%m%d")}.csv"')
        msg.attach(part)
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [to_email], msg.as_string())
        server.quit()
        return True, "達標報表已成功發送至您的電子郵件信箱！"
    except Exception as e:
        return False, f"自動發信失敗，錯誤原因: {e}"

def get_categories():
    doc = db.collection("system_settings").document("categories").get()
    if doc.exists:
        return doc.to_dict().get("list", [])
    else:
        default_list = ['學業優良', '熱心服務', '體育競賽', '藝文活動', '品德楷模', '其他']
        db.collection("system_settings").document("categories").set({"list": default_list})
        return default_list

def add_merit_point(teacher_id, teacher_role, student_id, category, reason, points=1):
    today_str = datetime.now().strftime("%Y-%m-%d")
    student_doc = db.collection("users").document(student_id).get()
    if not student_doc.exists:
        return False, f"找不到學號為 {student_id} 的學生"
    
    s_data = student_doc.to_dict()
    if s_data.get("status") == "disabled":
        return False, f"學號 {student_id} 已被停用，無法登錄點數。"
        
    if teacher_role not in ["admin", "coordinator"]:
        duplicate_check = db.collection("point_logs").where("teacher_id", "==", teacher_id)\
                                  .where("student_id", "==", student_id)\
                                  .where("date_str", "==", today_str).limit(1).get()
        if len(duplicate_check) > 0:
            return False, f"{s_data.get('name')} 今日已達上限（每天限給同一位學生 1 點）"
    
    fb_batch = db.batch()
    log_ref = db.collection("point_logs").document()
    fb_batch.set(log_ref, {
        "teacher_id": teacher_id,
        "student_id": student_id,
        "category": category,
        "reason": reason,
        "points": points, 
        "timestamp": firestore.SERVER_TIMESTAMP,
        "date_str": today_str
    })
    student_ref = db.collection("users").document(student_id)
    fb_batch.update(student_ref, {"total_points": firestore.Increment(points)}) 
    
    fb_batch.commit()
    return True, "登錄成功"

# ==========================================
# 5. Streamlit 狀態管理
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_info = None
if "auth_page" not in st.session_state:
    st.session_state.auth_page = "login"

if not st.session_state.logged_in and "login_token" in st.query_params:
    try:
        token_str = st.query_params["login_token"]
        if ":" in token_str:
            q_username, q_token = token_str.split(":", 1)
            cached_user = verify_session_token(q_username, q_token)
            if cached_user:
                st.session_state.logged_in = True
                st.session_state.user_info = cached_user
    except Exception:
        pass  

# ==========================================
# 6. 驗證與登入介面分流 (🌊 全螢幕海洋背景 x 懸浮毛玻璃卡片版)
# ==========================================
if not st.session_state.logged_in:
    import base64
    import os

    img_filename = "web-0.png"
    if not os.path.exists(img_filename) and os.path.exists("web-0.webp"):
        img_filename = "web-0.webp"
        
    img_base64 = ""
    if os.path.exists(img_filename):
        with open(img_filename, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()

    st.markdown(f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image: url("data:image/png;base64,{img_base64}");
            background-size: cover;
            background-position: center center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        [data-testid="stHeader"], [data-testid="stMainBlockContainer"] {{
            background: transparent !important;
        }}
        [data-testid="stMainBlockContainer"] {{
            padding-top: 6.5rem !important; 
        }}
        div[data-testid="column"]:nth-of-type(2) {{
            background: rgba(255, 255, 255, 0.88) !important; 
            padding: 2.5rem !important;
            border-radius: 24px !important;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2) !important;
            border: 1px solid rgba(255, 255, 255, 0.6) !important;
            backdrop-filter: blur(12px) !important; 
            -webkit-backdrop-filter: blur(12px) !important;
        }}
        div[data-testid="column"] div[data-testid="column"] {{
            background: transparent !important;
            padding: 0 !important;
            box-shadow: none !important;
            border: none !important;
            backdrop-filter: none !important;
        }}
        h2 {{ color: #0f4c81 !important; font-weight: 800 !important; margin-top: 0px !important; letter-spacing: 1px; }}
        h3 {{ color: #4a5568 !important; font-size: 1.05rem !important; font-weight: 500 !important; margin-bottom: 20px !important; }}
        .stTextInput label {{ color: #2d3748 !important; font-weight: 600 !important; }}
        .stTextInput {{ margin-bottom: -5px; }}
        </style>
    """, unsafe_allow_html=True)

    main_col1, main_col2 = st.columns([13, 9], gap="large")
    
    with main_col1:
        st.write("") 
        
    with main_col2:
        st.markdown("<h2>🏅 榮譽積點線上系統</h2>", unsafe_allow_html=True)
        st.markdown("<h3>⛵ 文昌國小 · 專屬登錄平台</h3>", unsafe_allow_html=True)
        st.write("---")

        if st.session_state.auth_page == "login":
            username = st.text_input("🔑 帳號 (學號 或 教師代碼)")
            password = st.text_input("🔒 密碼", type="password")

            st.write("")
            btn_col1, btn_col2 = st.columns([1, 1], gap="small")
            with btn_col1:
                if st.button("🚀 登入系統", type="primary", use_container_width=True):
                    user_doc = db.collection("users").document(username).get()
                    if user_doc.exists:
                        u_data = user_doc.to_dict()
                        if u_data.get("status") == "disabled":
                            st.error("🚫 您的帳號已被系統管理員停用，暫時無法登入。")
                        elif u_data.get("password") == password:
                            import uuid
                            new_token = str(uuid.uuid4())
                            db.collection("users").document(username).update({"session_token": new_token})
                            st.query_params["login_token"] = f"{username}:{new_token}"
                            
                            u_data["session_token"] = new_token
                            st.session_state.logged_in = True
                            st.session_state.user_info = u_data
                            st.rerun()
                        else:
                            st.error("密碼錯誤！")
                    else:
                        st.error("找不到該帳號，請洽管理員。")
            with btn_col2:
                if st.button("💡 忘記密碼？", use_container_width=True):
                    st.session_state.auth_page = "forgot_password"
                    st.rerun()

        elif st.session_state.auth_page == "forgot_password":
            st.markdown("<h4>🔒 忘記密碼 - 發送驗證碼</h4>", unsafe_allow_html=True)
            reset_user = st.text_input("請輸入您的帳號 (學號 或 教師代碼)")
            
            st.write("")
            btn_col1, btn_col2 = st.columns([1, 1], gap="small")
            with btn_col1:
                if st.button("發送驗證碼", type="primary", use_container_width=True):
                    if not reset_user:
                        st.warning("請先輸入帳號！")
                    else:
                        user_doc = db.collection("users").document(reset_user).get()
                        if user_doc.exists:
                            u_data = user_doc.to_dict()
                            if u_data.get("status") == "disabled":
                                st.error("🚫 該帳號已被停用，無法執行密碼重設。")
                            else:
                                user_email = u_data.get("email")
                                if user_email and "@" in user_email:
                                    code = str(random.randint(100000, 999999))
                                    success, msg = send_verification_email(user_email, code)
                                    if success:
                                        st.session_state.reset_username = reset_user
                                        st.session_state.reset_target_email = user_email
                                        st.session_state.reset_code = code
                                        st.session_state.auth_page = "verify_code"
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                                else:
                                    st.error("此帳號在系統中未綁定有效的 Email，請聯繫承辦人手動調整。")
                        else:
                            st.error("找不到該帳號，請重新確認。")
            with btn_col2:
                if st.button("返回登入畫面", use_container_width=True):
                    st.session_state.auth_page = "login"
                    st.rerun()

        elif st.session_state.auth_page == "verify_code":
            st.markdown("<h4>🔢 輸入郵件驗證碼</h4>", unsafe_allow_html=True)
            st.info(f"驗證碼已寄送至信箱：\n{st.session_state.reset_target_email}")
            input_code = st.text_input("請輸入 6 位數驗證碼", max_chars=6)
            
            st.write("")
            btn_col1, btn_col2 = st.columns([1, 1], gap="small")
            with btn_col1:
                if st.button("認證", type="primary", use_container_width=True):
                    if input_code == st.session_state.reset_code:
                        st.session_state.auth_page = "reset_password"
                        st.rerun()
                    else:
                        st.error("驗證碼不正確，請重新輸入！")
            with btn_col2:
                if f_btn := st.button("重新發送 / 返回", use_container_width=True):
                    st.session_state.auth_page = "forgot_password"
                    st.rerun()

        elif st.session_state.auth_page == "reset_password":
            st.markdown("<h4>✏️ 設定您的新密碼</h4>", unsafe_allow_html=True)
            new_pwd = st.text_input("請輸入新密碼", type="password")
            confirm_pwd = st.text_input("請再次輸入新密碼", type="password")
            
            st.write("")
            if st.button("儲存新密碼並登入", type="primary", use_container_width=True):
                if len(new_pwd) < 4:
                    st.error("密碼長度請至少設定 4 個字元以上。")
                elif new_pwd != confirm_pwd:
                    st.error("兩次輸入的新密碼不一致！")
                else:
                    db.collection("users").document(st.session_state.reset_username).update({
                        "password": new_pwd
                    })
                    st.success("🎉 密碼重設成功！請使用新密碼重新登入。")
                    st.session_state.auth_page = "login"
                    st.rerun()
                    
    st.stop()

# ==========================================
# 7. 主系統畫面 (登入後)
# ==========================================
user = st.session_state.user_info
role = user.get("role")

role_map = {"admin": "管理者", "coordinator": "業務承辦人", "teacher": "一般教師", "student": "學生"}

with st.sidebar:
    st.title("👤 個人資訊")
    st.write(f"**姓名**：{user.get('name')}")
    st.write(f"**帳號**：{user.get('username')}")
    st.write(f"**權限**：{role_map.get(role, '未知')}")
    
    if st.button("🚪 登出系統", use_container_width=True):
        if st.session_state.user_info:
            u_name = st.session_state.user_info.get("username")
            u_token = st.session_state.user_info.get("session_token")
            try:
                db.collection("users").document(u_name).update({"session_token": firestore.DELETE_FIELD})
                verify_session_token.clear(u_name, u_token)
            except:
                pass
        
        if "login_token" in st.query_params:
            del st.query_params["login_token"]
        st.session_state.logged_in = False
        st.session_state.user_info = None
        st.session_state.auth_page = "login"
        st.rerun()

st.title(f"🏆 榮譽積點系統 - {role_map.get(role)}")
st.write("---")

# ------------------------------------------
# 【學生功能】
# ------------------------------------------
if role == "student":
    st.header("📊 我的積點專區")
    student_logs = get_cached_student_logs(user["username"])
    
    user_doc = db.collection("users").document(user["username"]).get()
    pts = user_doc.to_dict().get("total_points", 0) if user_doc.exists else 0
    stages_config = get_cached_ocean_stages()
    avatar, stage_name, reward = get_student_avatar_and_stage(pts, stages_config)
    
    next_stage_text = "✨ 太棒了！你已達到最高榮譽頂峰！"
    for s in sorted(stages_config, key=lambda x: x["points"]):
        if s["points"] > pts:
            next_stage_text = f"💡 距離下一里程碑還差 **{s['points'] - pts}** 點 (下一目標：{s['stage']})"
            break

    # 💡 已修正：將代表圖案/Emoji 尺寸調降至原本的 15% 區間 (調整為精緻的 24px 排版)，並優化卡片空間提升美觀度
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%); padding: 15px 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom: 20px; display: flex; align-items: center;">
            <div style="font-size: 24px; line-height: 1; margin-right: 15px; display: flex; align-items: center; justify-content: center; min-width: 32px;">
                {avatar}
            </div>
            <div>
                <h2 style="margin: 0; color: #0369a1; font-size: 1.4rem; font-weight: 700;">目前海洋使命階級：【{stage_name}】</h2>
                <p style="margin: 4px 0 0 0; color: #0c4a6e; font-size: 1.0rem; font-weight: 600;">✨ 目前累計總積點：<span style="font-size: 1.2rem; color: #0284c7;">{pts}</span> 點</p>
            </div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    st.info(next_stage_text)
    
    if len(student_logs) == 0:
        st.info("目前尚無積點紀錄，繼續加油喔！")
    else:
        st.dataframe(pd.DataFrame(student_logs), use_container_width=True)

# ------------------------------------------
# 【教師 / 承辦人 / 管理者 通用給點功能】
# ------------------------------------------
if role in ["teacher", "coordinator", "admin"]:
    tab1, tab2, tab3 = st.tabs(["📝 單筆/批次登錄點數", "🏫 導師班級檢視", "🔍 我的登錄歷史"])
    categories = get_categories()
    
    with tab1:
        st.header("點數登錄面版")
        mode = st.radio("請選擇登錄模式：", ["依學號單筆登錄", "依班級全班/批次登錄"], horizontal=True)
        
        sel_category = st.selectbox("選擇優良表現分類", categories)
        reason = st.text_input("優良事由 / 備註说明", placeholder="例如：主動協助搬運體育器材")
        
        points_to_add = st.number_input("🔢 登錄點數設定", min_value=1, value=1, step=1)
        
        if mode == "依學號單筆登錄":
            s_id = st.text_input("請輸入學生學號：")
            if st.button("送出登錄", type="primary"):
                if s_id and sel_category:
                    success, msg = add_merit_point(user["username"], role, s_id.strip(), sel_category, reason, points=points_to_add)
                    if success: 
                        st.success(msg)
                        refresh_point_related_caches() 
                    else: 
                        st.error(msg)
                else:
                    st.warning("請填寫完整學號！")
                    
        else:
            classes = get_cached_active_classes()
            if not classes:
                st.warning("目 前系統內無 any 啟用的學生資料。")
            else:
                target_class = st.selectbox("選擇目標班級", classes)
                student_list = get_cached_students_by_class(target_class)
                
                if not student_list:
                    st.info("該班級目前沒有啟用的學生。")
                else:
                    st.write("---")
                    
                    def toggle_all_students():
                        all_checked = st.session_state[f"all_cb_{target_class}"]
                        for s in student_list:
                            st.session_state[f"chk_{target_class}_{s['id']}"] = all_checked

                    select_all = st.checkbox(
                        "✅ **全班選取 / 全班給點**", 
                        value=False, 
                        key=f"all_cb_{target_class}",
                        on_change=toggle_all_students
                    )
                    st.write("👉 **請勾選獲獎學生：**")
                    
                    selected_ids = []
                    grid_cols = st.columns(4) 
                    for idx, s in enumerate(student_list):
                        with grid_cols[idx % 4]:
                            is_checked = st.checkbox(s["label"], key=f"chk_{target_class}_{s['id']}")
                            if is_checked:
                                selected_ids.append(s["id"])
                    
                    st.write("---")
                    st.write(f"目前已選取 **{len(selected_ids)}** 位學生")
                    
                    if st.button("🚀 執行批次送出點數", type="primary"):
                        if not selected_ids:
                            st.warning("❌ 請至少勾選一位學生！")
                        else:
                            today_str = datetime.now().strftime("%Y-%m-%d")
                            
                            existing_today_ids = set()
                            if role not in ["admin", "coordinator"]:
                                existing_logs = db.collection("point_logs")\
                                                  .where("teacher_id", "==", user["username"])\
                                                  .where("date_str", "==", today_str).get()
                                existing_today_ids = {l.to_dict().get("student_id") for l in existing_logs}
                            
                            fb_batch = db.batch()
                            success_count = 0
                            fail_messages = []
                            
                            for s_id in selected_ids:
                                if role not in ["admin", "coordinator"] and s_id in existing_today_ids:
                                    fail_messages.append(f"學號 {s_id} 今日已達上限（每天限給同一位學生 1 點）")
                                    continue
                                
                                log_ref = db.collection("point_logs").document()
                                fb_batch.set(log_ref, {
                                    "teacher_id": user["username"],
                                    "student_id": s_id,
                                    "category": sel_category,
                                    "reason": reason,
                                    "points": points_to_add, 
                                    "timestamp": firestore.SERVER_TIMESTAMP,
                                    "date_str": today_str
                                })
                                
                                student_ref = db.collection("users").document(s_id)
                                fb_batch.update(student_ref, {"total_points": firestore.Increment(points_to_add)})
                                success_count += 1
                            
                            if success_count > 0:
                                fb_batch.commit()
                                st.success(f"🎉 處理完成！成功登錄 {success_count} 位學生的點數（每人各得 {points_to_add} 點）。")
                                refresh_point_related_caches() 
                            if fail_messages:
                                with st.expander("檢視未成功登錄名單"):
                                    for f_msg in fail_messages: st.error(f_msg)

    with tab2:
        st.header("🏫 級任導師專區")
        homeroom = user.get("homeroom_class")
        if not homeroom and role != "admin":
            st.info("系統紀錄您目前非級任導師。")
        else:
            if role == "admin":
                all_classes = get_cached_active_classes()
                if all_classes:
                    view_class = st.selectbox("管理員專屬：請選擇檢視班級", all_classes)
                else:
                    view_class = None
            else:
                view_class = homeroom
                st.success(f"您是 **{view_class}** 班的導師，以下為全班目前積點總計：")
            
            if view_class:
                report_data = get_cached_homeroom_report(view_class)
                if report_data:
                    df_report = pd.DataFrame(report_data).sort_values("座號")
                    st.dataframe(df_report, use_container_width=True, hide_index=True)
                else:
                    st.warning("該班級尚無學生資料。")
                    
            if st.button("🔄 手動重新整理班級數據"):
                refresh_all_system_caches()
                st.rerun()

    with tab3:
        st.header("🔍 我經手的登錄歷史紀錄")
        teacher_history = get_cached_teacher_logs(user["username"])
        if len(teacher_history) == 0:
            st.info("您近期沒有登錄 any 點數紀錄。")
        else:
            st.dataframe(pd.DataFrame(teacher_history), use_container_width=True)

# ==========================================
# ⚙️ 8. 管理與後台功能
# ==========================================
if role in ["admin", "coordinator"]:
    st.write("---")
    st.header("⚙️ 業務承辦與管理後台")
    
    # ------------------------------------------
    # 🎯【通用功能：開放給 管理者(admin) 與 業務承辦人(coordinator)】
    # ------------------------------------------
    with st.expander("📅 全校榮譽達標名單核算 (自動導出與 Mail 通知)"):
        st.subheader("🔍 依據現行設定門檻自動比對全校學生")
        st.write("系統將自動抓取目前執行中的所有海洋階段門檻值，並與全校學生當前總積點進行比對，自動匯出已跨越榮譽門檻之名單。")
        
        if st.button("🚀 執行自動化核算與郵件發送", type="primary"):
            with st.spinner("正在讀取全校學生數據並交叉核算中，請稍候..."):
                stages_config = get_cached_ocean_stages()
                all_students = db.collection("users").where("role", "==", "student").where("status", "==", "active").get()
                
                achieved_rows = []
                for s in all_students:
                    sd = s.to_dict()
                    u_pts = sd.get("total_points", 0)
                    
                    avatar, s_name, reward = get_student_avatar_and_stage(u_pts, stages_config)
                    
                    if s_name != "潛水初心階段":
                        achieved_rows.append({
                            "積點階段名稱": s_name,
                            "班級": sd.get("current_class", ""),
                            "座號": sd.get("current_seat_no", ""),
                            "學號": sd.get("username", ""),
                            "學生姓名": sd.get("name", ""),
                            "目前累計總積點": u_pts,
                            "應發放獎勵品項": reward
                        })
                
                if not achieved_rows:
                    st.info("💡 核算完成：目前全校尚無 any 學生達到最低的榮譽檻分數。")
                else:
                    df_achieved = pd.DataFrame(achieved_rows).sort_values(["班級", "座號"])
                    st.success(f"🎉 核算成功！目前全校共有 **{len(df_achieved)}** 位學生達標榮譽門檻。")
                    
                    st.dataframe(df_achieved, use_container_width=True, hide_index=True)
                    
                    csv_data = df_achieved.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 點此手動下載此達標名單 (CSV 檔案)",
                        data=csv_data,
                        file_name=f"全校榮譽階段達標總表_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                    
                    admin_email = user.get("email")
                    if admin_email and "@" in admin_email:
                        with st.spinner("✉️ 正在將達標名單打包為附件並發送至您的信箱..."):
                            mail_title = f"全校榮譽階段達標自動核算總表_{datetime.now().strftime('%Y-%m-%d')}"
                            mail_success, mail_msg = send_report_email_with_csv(admin_email, df_achieved, mail_title)
                            if mail_success:
                                f"📧 郵件發送成功！{mail_msg} (已寄至: {admin_email})"
                            else:
                                st.error(mail_msg)
                    else:
                        st.warning("⚠️ 提示：由於您目前的帳號資料內未綁定或填寫正確的 Email，系統無法執行自動寄信。")

    # ------------------------------------------
    # 核心新增功能：【📊 全校教師給點成效統計與圖表】(開放給管理者與承辦人)
    # ------------------------------------------
    with st.expander("📊 全校教師給點成效統計與圖表"):
        st.subheader("📈 追蹤榮譽計畫執行成效")
        st.write("此處分析全校所有具給點權限的人員（教師與管理端）發放點數之統計數據，並繪製成直觀的成效分析圖表。")
        
        if st.button("📊 生成全校教師績效圖表與數據"):
            with st.spinner("正在即時分析點數日誌（Point Logs），請稍候..."):
                # 1. 撈取所有教職員帳號建立基礎資料庫
                all_users_docs = db.collection("users").get()
                teachers_db = {}
                for u in all_users_docs:
                    ud = u.to_dict()
                    if ud.get("role") in ["teacher", "coordinator", "admin"]:
                        teachers_db[ud.get("username")] = {
                            "教師姓名": ud.get("name", "未命名"),
                            "身分別": role_map.get(ud.get("role"), "未知"),
                            "配屬導師班級": ud.get("homeroom_class", "無") or "無"
                        }
                
                # 2. 撈取所有點數變更紀錄進行加總分析
                all_logs_docs = db.collection("point_logs").get()
                points_counter = {}   # 儲存總點數
                tx_counter = {}       # 儲存給點次數
                
                for l in all_logs_docs:
                    ld = l.to_dict()
                    t_id = ld.get("teacher_id")
                    pts = int(ld.get("points", 1))
                    if t_id:
                        points_counter[t_id] = points_counter.get(t_id, 0) + pts
                        tx_counter[t_id] = tx_counter.get(t_id, 0) + 1
                
                # 3. 整合為 DataFrame
                stats_rows = []
                for t_id, info in teachers_db.items():
                    total_pts_sent = points_counter.get(t_id, 0)
                    total_tx_count = tx_counter.get(t_id, 0)
                    
                    stats_rows.append({
                        "教師代碼": t_id,
                        "教師姓名": info["教師姓名"],
                        "權限身分": info["身分別"],
                        "導師班級": info["配屬導師班級"],
                        "累計發放點數": total_pts_sent,
                        "累計給點次數": total_tx_count
                    })
                
                df_stats = pd.DataFrame(stats_rows)
                # 篩選掉從未發過點數的老師，僅呈現有執行成效的資料供圖表更清晰
                df_chart_active = df_stats[df_stats["累計發放點數"] > 0].sort_values(by="累計發放點數", ascending=False)
                
                if df_chart_active.empty:
                    st.info("💡 統計完成：目前全校教師尚未有任何給點日誌紀錄。")
                else:
                    st.success(f"🎉 數據統計完成！目前共有 {len(df_chart_active)} 位教職員積極參與給點。")
                    
                    # ---- 繪製成效圖表 ----
                    st.markdown("#### 🏆 教師給點排行累計圖")
                    # 將姓名和代碼結合以防同名同姓在圖表中重疊
                    df_chart_active["圖表呈現名稱"] = df_chart_active["教師姓名"] + " (" + df_chart_active["教師代碼"] + ")"
                    
                    # 建立適用於 st.bar_chart 的格式
                    chart_data = df_chart_active.set_index("圖表呈現名稱")[["累計發放點數"]]
                    st.bar_chart(chart_data)
                    
                    # ---- 資料數據總表與下載 ----
                    st.markdown("#### 📋 完整發放數據報表")
                    df_all_display = df_stats.sort_values(by="累計發放點數", ascending=False)
                    st.dataframe(df_all_display, use_container_width=True, hide_index=True)
                    
                    csv_stats_data = df_all_display.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 導出全校教師給點績效總表 (CSV 檔案)",
                        data=csv_stats_data,
                        file_name=f"全校教師榮譽點數發放統計_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )

    # ------------------------------------------
    # 🔒【限制區：唯有 最高管理者(admin) 才能檢視與操作以下進階系統設定】
    # ------------------------------------------
    if role == "admin":
        with st.expander("👥 使用者帳號管理（編輯資料 / 停用啟用）"):
            st.subheader("🔍 查詢與編輯師生帳號")
            
            search_mode = st.radio(
                "請選擇搜尋或篩選模式：", 
                ["依帳號(ID)搜尋", "依姓名關鍵字搜尋", "依班級篩選", "依身分別篩選"], 
                horizontal=True
            )
            
            matched_users = []  
            
            if search_mode == "依帳號(ID)搜尋":
                search_id = st.text_input("請輸入精確的使用者帳號 (學號或教師代碼)：").strip()
                if search_id:
                    doc = db.collection("users").document(search_id).get()
                    if doc.exists:
                        matched_users.append(doc)
                    else:
                        st.error(f"❌ 找不到帳號為 【{search_id}】 的使用者。")
                        
            elif search_mode == "依姓名關鍵字搜尋":
                search_name = st.text_input("請輸入姓名關鍵字（支援部分文字模糊查詢）：").strip()
                if search_name:
                    all_u = db.collection("users").limit(1500).get()
                    for u in all_u:
                        if search_name in u.to_dict().get("name", ""):
                            matched_users.append(u)
                    if not matched_users:
                        st.error(f"❌ 找不到姓名包含 【{search_name}】 的使用者。")
                        
            elif search_mode == "依班級篩選":
                all_u = db.collection("users").get()
                class_set = set()
                for u in all_u:
                    ud = u.to_dict()
                    if ud.get("current_class"): class_set.add(ud.get("current_class"))
                    if ud.get("homeroom_class"): class_set.add(ud.get("homeroom_class"))
                
                sorted_classes = sorted(list(class_set))
                if sorted_classes:
                    selected_search_class = st.selectbox("請選擇目標班級：", sorted_classes)
                    if selected_search_class:
                        for u in all_u:
                            ud = u.to_dict()
                            if ud.get("current_class") == selected_search_class or ud.get("homeroom_class") == selected_search_class:
                                matched_users.append(u)
                else:
                    st.info("目前資料庫中無班級紀錄。")
                    
            elif search_mode == "依身分別篩選":
                role_filter_map = {"student": "學生", "teacher": "一般教師", "coordinator": "業務承辦人", "admin": "最高管理者"}
                selected_role_key = st.selectbox("請選擇身分別角色：", list(role_filter_map.keys()), format_func=lambda x: role_filter_map[x])
                if selected_role_key:
                    results = db.collection("users").where("role", "==", selected_role_key).get()
                    matched_users = list(results)
            
            if matched_users:
                st.write(f"🔍 系統共找到 **{len(matched_users)}** 筆符合的資料：")
                
                user_options = []
                user_map = {}
                for u in matched_users:
                    ud = u.to_dict()
                    r_lbl = role_map.get(ud.get("role"), "未知")
                    cls_lbl = f"({ud.get('current_class') or ud.get('homeroom_class') or '無班級'})"
                    opt_text = f"{ud.get('username')} - {ud.get('name')} 【{r_lbl}】 {cls_lbl}"
                    user_options.append(opt_text)
                    user_map[opt_text] = u
                    
                selected_user_text = st.selectbox("👉 請從中選取一位進入下方表單編輯：", user_options)
                
                if selected_user_text:
                    target_doc = user_map[selected_user_text]
                    td = target_doc.to_dict()
                    
                    st.markdown(f"##### ✏️ 目前正在編輯：**{td.get('name')}** ({td.get('username')}) 的個人檔案")
                    with st.form(f"edit_form_{td.get('username')}", clear_on_submit=False):
                        col_u1, col_u2 = st.columns(2)
                        with col_u1:
                            edit_name = st.text_input("姓名", value=td.get("name", ""), key="e_name")
                            edit_password = st.text_input("登入密碼", value=td.get("password", ""), key="e_pwd")
                            edit_email = st.text_input("電子郵件 Email", value=td.get("email", ""), key="e_mail")
                        with col_u2:
                            role_options = ["student", "teacher", "coordinator", "admin"]
                            role_index = role_options.index(td.get("role", "student")) if td.get("role") in role_options else 0
                            edit_role = st.selectbox("系統權限角色", role_options, index=role_index, format_func=lambda x: role_map[x], key="e_role")
                            
                            current_status = td.get("status", "active")
                            status_options = ["active", "disabled"]
                            status_index = status_options.index(current_status) if current_status in status_options else 0
                            edit_status = st.radio("帳號狀態控制", status_options, index=status_index, format_func=lambda x: "🟢 啟用" if x == "active" else "🔴 停用", horizontal=True, key="e_status")

                        st.write("---")
                        col_u3, col_u4, col_u5 = st.columns(3)
                        with col_u3:
                            edit_class = st.text_input("學生：目前班級 (例如 101)", value=td.get("current_class", ""), key="e_class")
                        with col_u4:
                            edit_seat = st.text_input("學生：目前座號", value=td.get("current_seat_no", ""), key="e_seat")
                        with col_u5:
                            edit_homeroom = st.text_input("教師：級任班級 (例如 101)", value=td.get("homeroom_class", ""), key="e_hr")
                            
                        submit_changes = st.form_submit_button("💾 確認保存修改資料", type="primary")
                        if submit_changes:
                            if not edit_name or not edit_password:
                                st.error("姓名與密碼為必填欄位！")
                            else:
                                update_data = {
                                    "name": edit_name.strip(),
                                    "password": edit_password.strip(),
                                    "email": edit_email.strip(),
                                    "role": edit_role,
                                    "status": edit_status,
                                    "current_class": edit_class.strip(),
                                    "current_seat_no": edit_seat.strip().zfill(2) if edit_seat.strip() else "",
                                    "homeroom_class": edit_homeroom.strip()
                                }
                                db.collection("users").document(td.get("username")).update(update_data)
                                st.success(f"✅ 【{edit_name}】的資料更新成功！")
                                refresh_all_system_caches() 
                                st.rerun()

        with st.expander("🛠️ 榮譽積點分類調整設定"):
            current_cats = get_categories()
            st.write(f"**開立分類**： {', '.join(current_cats)}")
            new_cat = st.text_input("新增分類名稱：")
            if st.button("確認新增分類"):
                if new_cat and new_cat not in current_cats:
                    current_cats.append(new_cat)
                    db.collection("system_settings").document("categories").set({"list": current_cats})
                    st.success(f"已成功新增分類：{new_cat}")
                    refresh_all_system_caches()
                    st.rerun()

        with st.expander("🌊 晉級與海洋階段任務設定"):
            st.subheader("⚙️ 線上自訂/增刪榮譽階段與獎勵門檻")
            stages_list = get_cached_ocean_stages()
            
            st.markdown("##### 📊 目前系統運行中的階段列表總覽")
            display_rows = []
            for s in sorted(stages_list, key=lambda x: x["points"], reverse=True):
                lbl_avatar = "🖼️ 自訂圖標" if "<img" in s["avatar"] else s["avatar"]
                display_rows.append({
                    "達標總點數": s["points"],
                    "海洋階段名稱": s["stage"],
                    "代表頭像": lbl_avatar,
                    "解鎖品項描述": s["reward"]
                })
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
            
            st.write("---")
            st.markdown("##### ✏️ 編輯現有門檻或建立全新階段")
            
            dropdown_options = []
            for s in sorted(stages_list, key=lambda x: x["points"]):
                lbl_avatar = "🖼️ 圖標" if "<img" in s["avatar"] else s["avatar"]
                dropdown_options.append(f"修改項目：{s['points']} 點門檻 - {s['stage']} ({lbl_avatar})")
            dropdown_options.append("➕ 建立全新門檻階段")
            
            selected_choice = st.selectbox("👉 請選擇想要調整的門檻對象，或選取新增：", dropdown_options)
            
            if selected_choice == "➕ 建立全新門檻階段":
                default_pts = 0
                default_name = ""
                default_avatar = "🐟"
                default_reward = ""
                is_edit_mode = False
            else:
                parsed_pts = int(selected_choice.split("點門檻")[0].replace("修改項目：", "").strip())
                matched_stage = next((s for s in stages_list if s["points"] == parsed_pts), None)
                if matched_stage:
                    default_pts = matched_stage["points"]
                    default_name = matched_stage["stage"]
                    default_avatar = matched_stage["avatar"]
                    default_reward = matched_stage["reward"]
                else:
                    default_pts = 0
                    default_name = ""
                    default_avatar = "🐟"
                    default_reward = ""
                is_edit_mode = True
            
            with st.form("ocean_stage_dynamic_form", clear_on_submit=False):
                st.markdown("**🖋️ 請在下方調整欄位內容：**")
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    edit_pts = st.number_input("達標總點數門檻值 (必填識別代碼)", min_value=0, value=default_pts, step=10)
                    edit_stage_name = st.text_input("海洋階段名稱", value=default_name)
                with col_f2:
                    uploaded_badge = st.file_uploader("🏆 上傳新徽章圖片 (將自動裁切縮小並自適應排版)", type=["png", "jpg", "jpeg", "webp"])
                    is_html = "<img" in default_avatar
                    edit_avatar_emoji = st.text_input("或改用純文字/Emoji (若上方有上傳新圖片，系統將優先使用圖片)", value="" if is_html else default_avatar)
                    edit_reward = st.text_input("解鎖發放品項描述", value=default_reward)
                
                # 預覽處理
                preview_avatar = default_avatar
                if uploaded_badge is not None:
                    preview_avatar = "⏳ 儲存後將套用並顯示新上傳的徽章圖片"
                elif edit_avatar_emoji.strip():
                    preview_avatar = edit_avatar_emoji.strip()

                st.markdown(
                    f"""
                    <div style="background-color: #f8fafc; padding: 12px; border-radius: 8px; border: 1px dashed #cbd5e1; margin-top: 10px;">
                        <strong>✨ 目前 / 預覽圖標效果：</strong>
                        <div style="font-size: 24px; margin-top: 5px; line-height: 1; display: flex; align-items: center;">{preview_avatar}</div>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                st.write("")
                btn_c1, btn_c2 = st.columns([1, 4])
                with btn_c1:
                    save_submitted = st.form_submit_button("💾 儲存設定", type="primary")
                with btn_c2:
                    delete_submitted = st.form_submit_button("🗑️ 刪除此階段規則", type="secondary") if is_edit_mode else False
                
                if save_submitted:
                    if not edit_stage_name:
                        st.error("❌ 階段名稱欄位不能留空！")
                    else:
                        final_avatar = default_avatar  # 預設維持原本狀態
                        
                        # 💡 已修正：將上傳裁切的最大尺寸壓縮為 40x40 像素（大幅降低儲存容量，提升網頁載入速度）
                        if uploaded_badge is not None:
                            try:
                                img = Image.open(uploaded_badge)
                                img.thumbnail((40, 40))
                                buf = io.BytesIO()
                                img.save(buf, format="PNG")
                                b64_str = base64.b64encode(buf.getvalue()).decode()
                                # 💡 已修正：將 HTML 顯示大小設為優化的 24px
                                final_avatar = f'<img src="data:image/png;base64,{b64_str}" style="width:72px; height:72px; object-fit:contain; vertical-align:middle;" />'
                            except Exception as e:
                                st.error(f"❌ 圖片處理失敗，請重新確認檔案是否毀損。錯誤原因: {e}")
                                final_avatar = None
                        elif edit_avatar_emoji.strip():
                            final_avatar = edit_avatar_emoji.strip()
                        
                        if not final_avatar:
                            st.error("❌ 請提供代表頭像！請上傳圖檔或於下方欄位填入 Emoji 符號。")
                        else:
                            updated_stages = [s for s in stages_list if int(s["points"]) != int(edit_pts)]
                            if is_edit_mode and default_pts != edit_pts:
                                updated_stages = [s for s in updated_stages if int(s["points"]) != int(default_pts)]
                            
                            updated_stages.append({
                                "points": int(edit_pts),
                                "stage": edit_stage_name.strip(),
                                "avatar": final_avatar,
                                "reward": edit_reward.strip()
                            })
                            
                            db.collection("system_settings").document("ocean_stages").set({"stages": updated_stages})
                            st.success(f"🎉 成功儲存 {edit_pts} 點的海洋階段設定！")
                            refresh_all_system_caches()
                            st.rerun()
                        
                if delete_submitted:
                    updated_stages = [s for s in stages_list if int(s["points"]) != int(default_pts)]
                    db.collection("system_settings").document("ocean_stages").set({"stages": updated_stages})
                    st.success(f"🗑️ 已成功將 {default_pts} 點的階段規則自資料庫移除。")
                    refresh_all_system_caches()
                    st.rerun()

        with st.expander("📊 全校師名單 Excel 批次匯入"):
            st.subheader("上傳新學期 Excel 名單")
            import_type = st.radio("請選擇欲匯入的名單類型：", ["學生名單 (含新班級座號)", "教師名單 (含導師配置)"], horizontal=True)
            
            import os
            if import_type == "學生名單 (含新班級座號)":
                template_filename = "student-template.xlsx"
                template_label = "📥 下載 學生名單範例檔 (student-template.xlsx)"
            else:
                template_filename = "teacher-template.xlsx"
                template_label = "📥 下載 教師名單範例檔 (teacher-template.xlsx)"
                
            if os.path.exists(template_filename):
                with open(template_filename, "rb") as f:
                    st.download_button(
                        label=template_label,
                        data=f,
                        file_name=template_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_btn_{template_filename}" 
                    )
            else:
                st.caption(f"⚠️ 系統提示：主機根目錄內未偵測到實體檔案 `{template_filename}`。")
                
            st.write("") 
            uploaded_file = st.file_uploader("請選擇 Excel 檔案 (.xlsx)", type=["xlsx"])
            
            if uploaded_file is not None:
                try:
                    df = pd.read_excel(uploaded_file).fillna("")
                    df = df.astype(str).map(lambda x: x.strip())
                    st.write("📋 預覽即將匯入的資料：")
                    st.dataframe(df.head())
                    
                    if st.button("🚀 確認無誤，執行批次同步到 Firebase", type="primary"):
                        batch = db.batch()
                        success_count = 0
                        
                        if import_type == "學生名單 (含新班級座號)":
                            required_cols = ["username", "name", "password", "current_class", "current_seat_no", "email"]
                            if not all(c in df.columns for c in required_cols):
                                st.error(f"Excel 欄位不正確！必須包含：{required_cols}")
                            else:
                                for _, row in df.iterrows():
                                    doc_ref = db.collection("users").document(row["username"])
                                    batch.set(doc_ref, {
                                        "username": row["username"],
                                        "name": row["name"],
                                        "password": row["password"],
                                        "current_class": row["current_class"],
                                        "current_seat_no": str(row["current_seat_no"]).zfill(2),
                                        "email": row["email"],
                                        "role": "student",
                                        "status": "active",
                                        "total_points": 0  
                                    }, merge=True)
                                    success_count += 1
                                    if success_count % 400 == 0:
                                        batch.commit()
                                        batch = db.batch()
                        else:
                            required_cols = ["username", "name", "password", "homeroom_class", "email"]
                            if not all(c in df.columns for c in required_cols):
                                st.error(f"Excel 欄位不正確！必須包含：{required_cols}")
                            else:
                                for _, row in df.iterrows():
                                    doc_ref = db.collection("users").document(row["username"])
                                    batch.set(doc_ref, {
                                        "username": row["username"],
                                        "name": row["name"],
                                        "password": row["password"],
                                        "homeroom_class": row["homeroom_class"],
                                        "email": row["email"],
                                        "role": "teacher",
                                        "status": "active"
                                    }, merge=True)
                                    success_count += 1
                                    if success_count % 400 == 0:
                                        batch.commit()
                                        batch = db.batch()
                        
                        batch.commit()
                        st.success(f"🔥 同步成功！已處理 {success_count} 筆資料。")
                        refresh_all_system_caches() 
                        st.balloons()
                except Exception as e:
                    st.error(f"讀取檔案失敗。錯誤訊息: {e}")