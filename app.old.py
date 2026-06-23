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
# 將原本的 init_firebase 修改為以下內容：
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
# ⚡ 2. 🚀 高性能定向快取區
# ==========================================

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
            {"points": 1350, "stage": "菁英海洋階段", "avatar": "👑", "reward": "六級徽章"},
            {"points": 1250, "stage": "菁英海洋階段", "avatar": "👑", "reward": "校長室下午茶點心"},
            {"points": 1150, "stage": "菁英海洋階段", "avatar": "👑", "reward": "六級獎狀 1 張"},
            {"points": 1050, "stage": "深海探險階段", "avatar": "🦑", "reward": "五級榮譽徽章"},
            {"points": 960,  "stage": "深海探險階段", "avatar": "🦑", "reward": "五級獎狀 1 張"},
            {"points": 870,  "stage": "深海探險階段", "avatar": "🦑", "reward": "兌換券"},
            {"points": 780,  "stage": "大洋探險階段", "avatar": "🐋", "reward": "四級榮譽徽章"},
            {"points": 700,  "stage": "大洋探險階段", "avatar": "🐋", "reward": "四級獎狀 1 張"},
            {"points": 620,  "stage": "大洋探險階段", "avatar": "🐋", "reward": "兌換券"},
            {"points": 540,  "stage": "高級海洋階段", "avatar": "🦈", "reward": "三級榮譽徽章"},
            {"points": 470,  "stage": "高級海洋階段", "avatar": "🦈", "reward": "三級獎狀 1 張"},
            {"points": 400,  "stage": "高級海洋階段", "avatar": "🦈", "reward": "兌換券"},
            {"points": 330,  "stage": "中級海洋階段", "avatar": "🐠", "reward": "二級榮譽徽章"},
            {"points": 270,  "stage": "中級海洋階段", "avatar": "🐠", "reward": "二級獎狀 1 張"},
            {"points": 210,  "stage": "中級海洋階段", "avatar": "🐠", "reward": "兌換券 1 張"},
            {"points": 150,  "stage": "初級海洋階段", "avatar": "🐟", "reward": "一級榮譽徽章"},
            {"points": 100,  "stage": "初級海洋階段", "avatar": "🐟", "reward": "一級獎狀 1 張"},
            {"points": 50,   "stage": "初級海洋階段", "avatar": "🐟", "reward": "兌換券 1 張"}
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
        history.append({"日期": ld.get("date_str"), "學生學號": ld.get("student_id"), "分類": ld.get("category"), "事由": ld.get("reason")})
    return history

# ==========================================
# 🛠️ 3. 精準快取沖刷控制閥
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
    """【新增功能】將 DataFrame 轉為 CSV 並作為附件自動 E-mail 給管理者"""
    try:
        msg = MIMEMultipart()
        msg["Subject"] = f"🏅【校內榮譽積點系統】{report_title}"
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        
        # 信件本文
        body = f"您好：\n\n這是系統為您自動核算並導出的「{report_title}」。\n全校目前已達榮譽階級門檻之學生名單詳見附件 CSV 檔案。\n\n提示：附件已採用內置 UTF-8-BOM 編碼，您可直接使用 Excel 雙擊開啟，絕不卡中文亂碼。\n\n系統自動發送信件 - 請勿直接回覆"
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        # 轉換 CSV 資料夾帶
        csv_data = df.to_csv(index=False).encode('utf-8-sig')
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(csv_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="Honor_Milestone_Report_{datetime.now().strftime("%Y%m%d")}.csv"')
        msg.attach(part)
        
        # 發信
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

def add_merit_point(teacher_id, teacher_role, student_id, category, reason):
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
        "timestamp": firestore.SERVER_TIMESTAMP,
        "date_str": today_str
    })
    student_ref = db.collection("users").document(student_id)
    fb_batch.update(student_ref, {"total_points": firestore.Increment(1)})
    
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

# ==========================================
# 6. 驗證與登入介面分流
# ==========================================
if not st.session_state.logged_in:
    st.title("🏅 校內榮譽積點線上登錄系統")
    
    if st.session_state.auth_page == "login":
        st.subheader("請登入系統")
        username = st.text_input("帳號 (學號 或 教師代碼)")
        password = st.text_input("密碼", type="password")
        
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("登入", type="primary"):
                user_doc = db.collection("users").document(username).get()
                if user_doc.exists:
                    u_data = user_doc.to_dict()
                    if u_data.get("status") == "disabled":
                        st.error("🚫 您的帳號已被系統管理員停用，暫時無法登入。")
                    elif u_data.get("password") == password:
                        st.session_state.logged_in = True
                        st.session_state.user_info = u_data
                        st.rerun()
                    else:
                        st.error("密碼錯誤！")
                else:
                    st.error("找不到該帳號，請洽管理员。")
        with col2:
            if st.button("忘記密碼？"):
                st.session_state.auth_page = "forgot_password"
                st.rerun()

    elif st.session_state.auth_page == "forgot_password":
        st.subheader("🔒 忘記密碼 - 發送驗證碼")
        reset_user = st.text_input("請輸入您的帳號 (學號 或 教師代碼)")
        
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("發送驗證碼", type="primary"):
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
        with col2:
            if st.button("返回登入畫面"):
                st.session_state.auth_page = "login"
                st.rerun()

    elif st.session_state.auth_page == "verify_code":
        st.subheader("🔢 輸入郵件驗證碼")
        st.info(f"驗證碼已寄送至您的信箱：{st.session_state.reset_target_email}，請查收。")
        input_code = st.text_input("請輸入信件中的 6 位數驗證碼", max_chars=6)
        
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("認證", type="primary"):
                if input_code == st.session_state.reset_code:
                    st.session_state.auth_page = "reset_password"
                    st.rerun()
                else:
                    st.error("驗證碼不正確，請重新輸入！")
        with col2:
            if st.button("重新發送/返回"):
                st.session_state.auth_page = "forgot_password"
                st.rerun()

    elif st.session_state.auth_page == "reset_password":
        st.subheader("✏️ 設定您的新密碼")
        new_pwd = st.text_input("請輸入新密碼", type="password")
        confirm_pwd = st.text_input("請再次輸入新密碼", type="password")
        
        if st.button("儲存新密碼並登入", type="primary"):
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
    
    if st.button("登出系統"):
        st.session_state.logged_in = False
        st.session_state.user_info = None
        st.session_state.auth_page = "login"
        st.rerun()

st.title(f"🏆 榮譽積點系統 - {role_map.get(role)}")
st.write("---")

# ------------------------------------------
# 【學生功能 - 保留精美大頭像與進度卡】
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

    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%); padding: 25px; border-radius: 16px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom: 25px; display: flex; align-items: center;">
            <div style="font-size: 72px; line-height: 1; margin-right: 25px; display: flex; align-items: center; justify-content: center; min-width: 80px;">
                {avatar}
            </div>
            <div>
                <h2 style="margin: 0; color: #0369a1; font-size: 1.8rem; font-weight: 700;">目前海洋使命階級：【{stage_name}】</h2>
                <p style="margin: 8px 0 0 0; color: #0c4a6e; font-size: 1.2rem; font-weight: 600;">✨ 目前累計總積點：<span style="font-size: 1.5rem; color: #0284c7;">{pts}</span> 點</p>
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
        
        if mode == "依學號單筆登錄":
            s_id = st.text_input("請輸入學生學號：")
            if st.button("送出登錄", type="primary"):
                if s_id and sel_category:
                    success, msg = add_merit_point(user["username"], role, s_id.strip(), sel_category, reason)
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
                st.warning("目前系統內無任何啟用的學生資料。")
            else:
                target_class = st.selectbox("選擇目標班級", classes)
                student_list = get_cached_students_by_class(target_class)
                
                if not student_list:
                    st.info("該班級目前沒有啟用的學生。")
                else:
                    st.write("---")
                    select_all = st.checkbox("✅ **全班選取 / 全班給點**", value=False, key=f"all_cb_{target_class}")
                    st.write("👉 **請勾選獲獎學生：**")
                    
                    selected_ids = []
                    grid_cols = st.columns(4) 
                    for idx, s in enumerate(student_list):
                        with grid_cols[idx % 4]:
                            is_checked = st.checkbox(s["label"], value=select_all, key=f"chk_{target_class}_{s['id']}")
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
                                    "timestamp": firestore.SERVER_TIMESTAMP,
                                    "date_str": today_str
                                })
                                
                                student_ref = db.collection("users").document(s_id)
                                fb_batch.update(student_ref, {"total_points": firestore.Increment(1)})
                                success_count += 1
                            
                            if success_count > 0:
                                fb_batch.commit()
                                st.success(f"🎉 處理完成！成功登錄 {success_count} 位學生的點數。")
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
    # 🎯 【全新優化需求：依現行設定門檻全自動導出與寄信通知】
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
                    
                    # 核對該生目前的階段、頭像與品項
                    avatar, s_name, reward = get_student_avatar_and_stage(u_pts, stages_config)
                    
                    # 只要不是最低的初始「潛水初心階段」，就代表該生至少達到一項現行門檻，將其納入導出範圍
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
                    st.info("💡 核算完成：目前全校尚無任何學生達到最低的榮譽檻分數。")
                else:
                    df_achieved = pd.DataFrame(achieved_rows).sort_values(["班級", "座號"])
                    st.success(f"🎉 核算成功！目前全校共有 **{len(df_achieved)}** 位學生達標榮譽門檻。")
                    
                    # 1. 呈現列表供網頁端直接檢視
                    st.dataframe(df_achieved, use_container_width=True, hide_index=True)
                    
                    # 2. 供管理者在線上直接下載
                    csv_data = df_achieved.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 點此手動下載此達標名單 (CSV 檔案)",
                        data=csv_data,
                        file_name=f"全校榮譽階段達標總表_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                    
                    # 3. 自動將匯出的資料信件 Mail 給目前登入的管理者
                    admin_email = user.get("email")
                    if admin_email and "@" in admin_email:
                        with st.spinner("✉️ 正在將達標名單打包為附件並發送至您的信箱..."):
                            mail_title = f"全校榮譽階段達標自動核算總表_{datetime.now().strftime('%Y-%m-%d')}"
                            mail_success, mail_msg = send_report_email_with_csv(admin_email, df_achieved, mail_title)
                            if mail_success:
                                st.success(f"📧 郵件發送成功！{mail_msg} (已寄至: {admin_email})")
                            else:
                                st.error(mail_msg)
                    else:
                        st.warning("⚠️ 提示：由於您目前的帳號資料內未綁定或填寫正確的 Email，系統無法執行自動寄信。請在下方帳號管理中為自己填寫電子郵件。")

    with st.expander("👥 使用者帳號管理（編輯資料 / 停用啟用）"):
        st.subheader("🔍 查詢與編輯師生帳號")
        search_mode = st.radio("搜尋方式", ["依帳號(ID)搜尋", "依姓名搜尋"], horizontal=True)
        search_input = st.text_input(f"請輸入關鍵字：", key="user_search_input_new").strip()
        
        target_doc = None
        if search_input:
            if search_mode == "依帳號(ID)搜尋":
                target_doc = db.collection("users").document(search_input).get()
                if not target_doc.exists:
                    st.error(f"❌ 找不到帳號為 【{search_input}】 的使用者。")
            else:
                results = db.collection("users").where("name", "==", search_input).limit(1).get()
                if len(results) > 0:
                    target_doc = results[0]
                else:
                    st.error(f"❌ 找不到姓名為 【{search_input}】 的使用者。")
        
        if target_doc and target_doc.exists:
            td = target_doc.to_dict()
            st.success(f"🎉 已成功找到 【{td.get('name')}】 的帳號資料：")
            
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
                    edit_class = st.text_input("學生：目前班級", value=td.get("current_class", ""), key="e_class")
                with col_u4:
                    edit_seat = st.text_input("學生：目前座號", value=td.get("current_seat_no", ""), key="e_seat")
                with col_u5:
                    edit_homeroom = st.text_input("教師：級任班級", value=td.get("homeroom_class", ""), key="e_hr")
                    
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
                        st.success(f"✅ 資料更新成功！")
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

    # ------------------------------------------
    # 🌊 【動態下拉式階段管理介面】
    # ------------------------------------------
    if role == "admin":
        with st.expander("🌊 晉級與海洋階段任務設定 (最高管理者專屬)"):
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
                    edit_avatar = st.text_input("代表頭像 (可填 Emoji，或直接貼入 HTML 圖片代碼如 <img src='網址' width='48'>)", value=default_avatar)
                    edit_reward = st.text_input("解鎖發放品項描述", value=default_reward)
                
                st.markdown(
                    f"""
                    <div style="background-color: #f8fafc; padding: 12px; border-radius: 8px; border: 1px dashed #cbd5e1; margin-top: 10px;">
                        <strong>✨ 圖標預覽效果 (系統會自動以 48px ~ 72px 放大顯示)：</strong>
                        <div style="font-size: 48px; margin-top: 5px; line-height: 1;">{edit_avatar}</div>
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
                    if not edit_stage_name or not edit_avatar:
                        st.error("❌ 階段名稱與代表頭像欄位不能留空！")
                    else:
                        updated_stages = [s for s in stages_list if int(s["points"]) != int(edit_pts)]
                        if is_edit_mode and default_pts != edit_pts:
                            updated_stages = [s for s in updated_stages if int(s["points"]) != int(default_pts)]
                        
                        updated_stages.append({
                            "points": int(edit_pts),
                            "stage": edit_stage_name.strip(),
                            "avatar": edit_avatar.strip(),
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

    with st.expander("📊 全校師生名單 Excel 批次匯入"):
        st.subheader("上傳新學期 Excel 名單")
        import_type = st.radio("請選擇欲匯入的名單類型：", ["學生名單 (含新班級座號)", "教師名單 (含導師配置)"], horizontal=True)
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
