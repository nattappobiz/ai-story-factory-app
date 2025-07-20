import os
import time
import requests
from google.cloud import firestore
from tenacity import retry, stop_after_attempt, wait_fixed

# --- 1. การตั้งค่า (Configuration) ---
print("🚀 Starting Script Writer Worker (v2.0 with Retry Logic)...")

# ตั้งค่าการเชื่อมต่อ Google Cloud (อ่านไฟล์ key โดยตรง)
# ตรวจสอบให้แน่ใจว่า Path และชื่อไฟล์ถูกต้อง
GCP_KEY_FILE_PATH = "E:\\streamlit-story-app\\youtubeubload.json"
GCP_PROJECT_ID = "youtubeubload"

# ตรวจสอบให้แน่ใจว่า URL ของ Replit API ถูกต้อง
REPLIT_API_URL = "https://83ad9944-9259-4aa1-a670-43bf9d023e8e-00-2bt3s9wflkig.worf.replit.dev/generate"

try:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GCP_KEY_FILE_PATH
    if not os.path.exists(GCP_KEY_FILE_PATH):
        raise FileNotFoundError(f"Key file not found at: {GCP_KEY_FILE_PATH}")
    
    # เชื่อมต่อกับ Firestore
    db = firestore.Client(project=GCP_PROJECT_ID)
    print("✅ Successfully connected to Firestore.")
except Exception as e:
    print(f"❌ Worker failed to initialize: {e}")
    exit() # ออกจากโปรแกรมถ้าตั้งค่าไม่สำเร็จ


# --- 2. ฟังก์ชันการทำงานหลักของ Worker ---

# Decorator @retry จะทำงานกับฟังก์ชันนี้โดยเฉพาะ
# ถ้าฟังก์ชันนี้เกิด Exception (เช่น HTTP 503), tenacity จะสั่งให้รันฟังก์ชันนี้ใหม่
@retry(
    stop=stop_after_attempt(3), # พยายามใหม่สูงสุด 3 ครั้ง
    wait=wait_fixed(15), # แต่ละครั้งให้รอ 15 วินาที (เพื่อให้ Replit มีเวลาตื่น)
    reraise=True # ถ้าลองครบ 3 ครั้งแล้วยังพลาด ให้โยน Error สุดท้ายออกมา
)
def call_replit_api(topic, style):
    """
    ฟังก์ชันสำหรับเรียก Replit API โดยเฉพาะ (เพื่อให้ retry ทำงานถูกจุด)
    """
    print("    - Attempting to call Replit API...")
    payload = {"topic": topic, "style": style}
    response = requests.post(REPLIT_API_URL, json=payload, timeout=90) # เพิ่ม timeout เป็น 90 วิ
    response.raise_for_status() # ถ้าเจอ Error (เช่น 4xx, 5xx), tenacity จะดักจับและสั่งให้ลองใหม่
    print("    - Call to Replit API successful.")
    return response.json()


def process_script_request(doc_id, doc_data):
    """
    รับข้อมูลโปรเจกต์, เรียก Replit API, และอัปเดต Firestore
    """
    print(f"  - Processing project: {doc_id}")
    topic = doc_data.get('topic')
    style = doc_data.get('style')

    if not topic:
        print(f"  - ❌ Error: Topic is missing in project {doc_id}. Marking as failed.")
        db.collection('projects').document(doc_id).update({'status': 'script_failed', 'error_message': 'Topic is missing'})
        return

    try:
        # เรียกฟังก์ชันใหม่ที่มี @retry ครอบอยู่
        story_data = call_replit_api(topic, style)
        
        scenes = story_data.get("scenes")
        if not scenes:
            raise ValueError("Replit API response did not contain a 'scenes' key.")

        # อัปเดต Document ใน Firestore
        print(f"  - Received {len(scenes)} scenes. Updating Firestore for project {doc_id}...")
        db.collection('projects').document(doc_id).update({
            'scenes': scenes,
            'status': 'assets_pending', # <-- เปลี่ยนสถานะเพื่อส่งต่องานให้แผนกถัดไป
            'script_completed_at': firestore.SERVER_TIMESTAMP,
            'error_message': firestore.DELETE_FIELD # ลบฟิลด์ error ถ้ามี
        })
        print(f"  - ✅ Project {doc_id} script generation completed successfully.")

    except Exception as e:
        error_message = f"Failed after multiple retries: {e}"
        print(f"  - ❌ An error occurred for project {doc_id}: {error_message}")
        db.collection('projects').document(doc_id).update({
            'status': 'script_failed',
            'error_message': error_message
        })


# --- 3. Main Loop: วงจรการทำงานที่ไม่สิ้นสุด ---
def main_loop():
    print("\n👂 Worker is listening for new projects with status 'script_pending'...")
    while True:
        try:
            # Query หาโปรเจกต์ที่ยังรอทำบท
            projects_ref = db.collection('projects')
            # หมายเหตุ: UserWarning ที่เกิดขึ้นตรงนี้เป็นเรื่องปกติของ Library และไม่มีผลกับการทำงาน
            query = projects_ref.where('status', '==', 'script_pending').limit(1) 
            docs = query.stream()

            found_job = False
            for doc in docs:
                found_job = True
                doc_id = doc.id
                print(f"\n✨ Found a new job! Project ID: {doc_id}")
                
                # ล็อคงานโดยการเปลี่ยนสถานะทันที
                projects_ref.document(doc_id).update({'status': 'script_processing'})
                
                # เริ่มทำงาน
                process_script_request(doc_id, doc.to_dict())
            
            if not found_job:
                # ถ้าไม่เจองาน, ให้รอสักครู่ก่อนถามใหม่
                # พิมพ์ . เพื่อให้รู้ว่ายังทำงานอยู่
                print(".", end="", flush=True) 
                time.sleep(10) # รอ 10 วินาที

        except Exception as e:
            print(f"\n\n🚨 An critical error occurred in the main loop: {e}\n\n")
            time.sleep(30) # ถ้าเกิด Error ใหญ่ ให้รอ 30 วินาทีก่อนลองใหม่

if __name__ == "__main__":
    main_loop()