import streamlit as st
import os
from datetime import datetime
from google.cloud import firestore

# --- 1. การตั้งค่าหน้าเว็บและ GCP ---
st.set_page_config(page_title="AI Story Factory", page_icon="🏭", layout="wide")

# ใช้วิธีอ่านไฟล์ตรง (ยังคงปลอดภัยสำหรับการรันบนเครื่องตัวเอง)
GCP_KEY_FILE_PATH = "E:\\streamlit-story-app\\youtubeubload.json"
GCP_PROJECT_ID = "youtubeubload"

@st.cache_resource
def connect_to_firestore():
    """
    สร้างการเชื่อมต่อกับ Firestore และ cache ไว้เพื่อไม่ให้เชื่อมต่อใหม่ทุกครั้ง
    """
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GCP_KEY_FILE_PATH
        if not os.path.exists(GCP_KEY_FILE_PATH):
            return None, f"ไม่พบไฟล์ Key ที่: {GCP_KEY_FILE_PATH}"
        
        db = firestore.Client(project=GCP_PROJECT_ID)
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
                else:
                    st.warning("Please enter a topic.")

    st.divider()

    # --- ส่วนที่ 3.2: Dashboard สำหรับติดตามโปรเจกต์ ---
    st.header("📊 Production Line Monitoring")

    if st.button("🔄 Refresh Project List"):
        # ไม่ต้องทำอะไร Streamlit จะ rerun เองเมื่อปุ่มถูกกด
        pass

    # ดึงข้อมูลและแสดงผล
    projects = fetch_projects()
    
    if not projects:
        st.info("No projects in the production line yet. Create a new order above!")
    else:
        for project in projects:
            with st.container(border=True):
                # ... (โค้ดแสดง topic, style, status เหมือนเดิม) ...
                
                final_url = project.get("final_video_url")
                if final_url:
                    # --- ส่วนที่เปลี่ยนแปลง ---
                    # เราจะไม่ใช้ st.video อีกต่อไป เพราะมันอาจจะเล่น Signed URL ไม่ได้
                    # st.video(final_url) 
                    
                    st.success("🎉 Your video is ready!")
                    st.info("Click the button below to open and watch your video in a new tab. The link will expire in 1 hour.")
                    
                    # สร้างปุ่มลิงก์ที่ชัดเจน
                    st.link_button("🎬 **Watch Your Video**", final_url)
                    # ---------------------------
                
                # (ทางเลือก) แสดงรายละเอียดเพิ่มเติมถ้าล้มเหลว
                error_msg = project.get("error_message")
                if error_msg:
                    with st.expander("View Error Details"):
                        st.error(error_msg)