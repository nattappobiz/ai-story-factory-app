import streamlit as st
import os
import json
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account # <-- Import ที่สำคัญ

# --- 1. การตั้งค่าหน้าเว็บและ GCP (สำหรับ Cloud เท่านั้น) ---
st.set_page_config(page_title="AI Story Factory", page_icon="🏭", layout="wide")

@st.cache_resource
def connect_to_firestore():
    """
    สร้างการเชื่อมต่อกับ Firestore โดยใช้ Streamlit Secrets เท่านั้น
    """
    try:
        # สร้าง credentials object จาก st.secrets โดยตรง
        creds_dict = dict(st.secrets.gcp_service_account)
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        project_id = creds_dict.get("project_id")
        
        db = firestore.Client(project=project_id, credentials=credentials)
        return db, None
        
    except Exception as e:
        error_details = (
            "Could not connect to Firestore using Streamlit Secrets. "
            "Please check the following:\n"
            "1. You have a [gcp_service_account] section in your secrets.\n"
            "2. All keys from your JSON file are correctly copied into the secrets.\n"
            f"3. Underlying error: {e}"
        )
        return None, error_details

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

@st.cache_data(ttl=60)
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
            topic = st.text_input("Topic:", "a brave knight and a friendly dragon")
            style = st.text_input("Style:", "an epic fantasy")
            
            submitted = st.form_submit_button("🚀 SUBMIT ORDER TO FACTORY")
            
            if submitted:
                if topic:
                    with st.spinner("Submitting order..."):
                        project_id = create_story_project(topic, style)
                        if project_id:
                            st.success(f"Order submitted! Project ID: {project_id}")
                            st.balloons()
                            st.cache_data.clear()
                else:
                    st.warning("Please enter a topic.")

    st.divider()

    # --- ส่วนที่ 3.2: Dashboard สำหรับติดตามโปรเจกต์ ---
    st.header("📊 Production Line Monitoring")

    if st.button("🔄 Refresh Project List"):
        st.cache_data.clear()
        st.rerun()

    projects = fetch_projects()
    
    if not projects:
        st.info("No projects in the production line yet.")
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

                final_url = project.get("final_video_url")
                if final_url:
                    st.info("Your video is ready! The link expires in 1 hour.")
                    st.link_button("🎬 **Watch Your Video**", final_url)
                
                error_msg = project.get("error_message")
                if error_msg:
                    with st.expander("View Error Details"):
                        st.error(error_msg)
