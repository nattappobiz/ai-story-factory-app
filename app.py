import streamlit as st
import os
import json # <-- เพิ่ม import นี้
from datetime import datetime
from google.cloud import firestore

# --- 1. การตั้งค่าหน้าเว็บและ GCP (เวอร์ชัน Hybrid ที่เข้ากันได้กับ Cloud) ---
st.set_page_config(page_title="AI Story Factory", page_icon="🏭", layout="wide")

@st.cache_resource
def connect_to_firestore():
    """
    สร้างการเชื่อมต่อกับ Firestore โดยลองใช้ Secrets ก่อน, ถ้าไม่เจอก็ใช้ไฟล์ Local
    """
    try:
        # วิธีที่ 1: พยายามใช้ Streamlit Secrets (สำหรับตอน Deploy)
        # จะมองหา Header [gcp]
        if "gcp" in st.secrets:
            project_id = st.secrets["gcp"]["project_id"]
            creds_json_str = st.secrets["gcp"]["credentials_json"]
            
            # สร้างไฟล์ credentials ชั่วคราวจาก secret string
            with open("gcp_creds.json", "w") as f:
                f.write(creds_json_str)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp_creds.json"
            
            db = firestore.Client(project=project_id)
            return db, None

        # วิธีที่ 2: ถ้าไม่เจอ Secrets, ให้ใช้ไฟล์ Local (สำหรับรันบนเครื่องตัวเอง)
        else:
            local_key_path = "youtubeubload.json"
            if not os.path.exists(local_key_path):
                return None, f"ไม่พบไฟล์ Key ที่: {local_key_path}"
            
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_key_path
            
            with open(local_key_path, 'r') as f:
                creds = json.load(f)
                project_id = creds.get('project_id')

            db = firestore.Client(project=project_id)
            return db, None
            
    except Exception as e:
        return None, f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {e}"

# เชื่อมต่อฐานข้อมูล
db, error_message = connect_to_firestore()

# --- 2. ฟังก์ชัน Helper ---
def create_story_project(topic: str, style: str):
    """สร้าง Document ใหม่ใน Firestore collection 'projects'"""
    if not db:
        st.error("ไม่ได้เชื่อมต่อกับฐานข้อมูล Firestore")
        return None
    try:
        projects_ref = db.collection('projects')
        project_data = {
            'topic': topic,
            'style': style,
            'status': 'script_pending',
            'created_at': firestore.SERVER_TIMESTAMP,
        }
        update_time, doc_ref = projects_ref.add(project_data)
        return doc_ref.id
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการสร้างโปรเจกต์: {e}")
        return None

@st.cache_data(ttl=60) # Cache ผลลัพธ์ไว้ 60 วินาทีเพื่อลดการอ่านจาก DB
def fetch_projects():
    """ดึงข้อมูลโปรเจกต์ทั้งหมดจาก Firestore"""
    if not db:
        return []
    try:
        projects_ref = db.collection('projects')
        docs = projects_ref.order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        
        project_list = []
        for doc in docs:
            project_data = doc.to_dict()
            project_data['id'] = doc.id
            project_list.append(project_data)
        return project_list
    except Exception as e:
        st.error(f"ไม่สามารถดึงข้อมูลโปรเจกต์ได้: {e}")
        return []

# --- 3. ส่วน UI ของ Streamlit ---

st.title("🏭 AI Story Factory - Command Center")

if not db:
    st.error(f"ไม่สามารถเริ่มต้นแอปพลิเคชันได้: {error_message}")
else:
    # --- ส่วนที่ 3.1: Form สำหรับสร้าง Order ใหม่ ---
    with st.expander("📝 **Create a New Story Order**", expanded=True):
        with st.form("story_order_form", clear_on_submit=True):
            st.subheader("Order Details")
            topic = st.text_input("Topic:", "a dragon who is afraid of heights")
            style = st.text_input("Style:", "a comedy adventure")
            
            submitted = st.form_submit_button("🚀 SUBMIT ORDER TO FACTORY")
            
            if submitted:
                if topic:
                    with st.spinner("Submitting order to the production line..."):
                        project_id = create_story_project(topic, style)
                        if project_id:
                            st.success(f"Order submitted successfully! Project ID: {project_id}")
                            st.balloons()
                            # Clear cache to show new project immediately
                            st.cache_data.clear()
                else:
                    st.warning("Please enter a topic.")

    st.divider()

    # --- ส่วนที่ 3.2: Dashboard สำหรับติดตามโปรเจกต์ ---
    st.header("📊 Production Line Monitoring")

    if st.button("🔄 Refresh Project List"):
        # Clear cache to force a re-fetch from Firestore
        st.cache_data.clear()
        st.rerun()

    # ดึงข้อมูลและแสดงผล
    projects = fetch_projects()
    
    if not projects:
        st.info("No projects in the production line yet. Create a new order above!")
    else:
        for project in projects:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.subheader(f'🎬 {project.get("topic", "N/A")}')
                    st.caption(f'Style: {project.get("style", "N/A")} | Project ID: {project.get("id")}')
                
                with col2:
                    status = project.get("status", "unknown")
                    if status == "completed":
                        st.success(f"✅ COMPLETED")
                    elif "failed" in status:
                        st.error(f"❌ FAILED")
                    else:
                        st.info(f"⏳ {status.upper()}")

                # แสดงวิดีโอถ้าเสร็จแล้ว
                final_url = project.get("final_video_url")
                if final_url:
                    st.info("Click the button below to watch your video. The link is temporary and will expire.")
                    st.link_button("🎬 **Watch Your Video**", final_url)
                
                # แสดงรายละเอียดเพิ่มเติมถ้าล้มเหลว
                error_msg = project.get("error_message")
                if error_msg:
                    with st.expander("View Error Details"):
                        st.error(error_msg)