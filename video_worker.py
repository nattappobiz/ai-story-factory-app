import os
import time
import requests
from google.cloud import firestore, storage
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
import datetime

# --- 1. การตั้งค่า ---
print("🚀 Starting Video Compiler Worker...")

# --- แก้ไขตรงนี้ให้ตรงกับ Worker ตัวอื่นๆ ---
GCP_KEY_FILE_PATH = "E:\\streamlit-story-app\\youtubeubload.json"
GCP_PROJECT_ID = "youtubeubload"
BUCKET_NAME = "ai-story-factory-assets-nattapobiz"
# ----------------------------------------------

TEMP_FOLDER = "temp_files"
if not os.path.exists(TEMP_FOLDER):
    os.makedirs(TEMP_FOLDER)

try:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GCP_KEY_FILE_PATH
    db = firestore.Client(project=GCP_PROJECT_ID)
    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    print("✅ Successfully connected to GCP services (Firestore, Storage).")
except Exception as e:
    print(f"❌ Worker failed to initialize: {e}")
    exit()

# --- 2. ฟังก์ชันการทำงานของ Worker ---

def download_from_gcs(source_blob_name, destination_file_name):
    """ดาวน์โหลดไฟล์จาก Google Cloud Storage"""
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)
    print(f"    - Downloaded: {source_blob_name}")

def upload_to_gcs(file_path, destination_blob_name):
    """อัปโหลดไฟล์ไปยัง Google Cloud Storage"""
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(file_path)
    print(f"    - Uploaded: {destination_blob_name}")
    return blob.public_url

def process_compile_request(doc_id, doc_data):
    scenes = doc_data.get('scenes', [])
    local_asset_paths = []
    
    # --- ขั้นตอนดาวน์โหลด ---
    print(f"  - Downloading assets for project {doc_id}...")
    for i, scene in enumerate(scenes):
        scene_num = i + 1
        image_url = scene.get('image_url')
        audio_url = scene.get('audio_url')
        
        if image_url and audio_url:
            local_image_path = os.path.join(TEMP_FOLDER, f"{doc_id}_scene_{scene_num}.png")
            local_audio_path = os.path.join(TEMP_FOLDER, f"{doc_id}_scene_{scene_num}.mp3")
            
            # ดึงชื่อไฟล์จาก URL (เช่น 'doc_id/scene_1.png')
            image_blob_name = "/".join(image_url.split("/")[4:])
            audio_blob_name = "/".join(audio_url.split("/")[4:])
            
            download_from_gcs(image_blob_name, local_image_path)
            download_from_gcs(audio_blob_name, local_audio_path)
            
            local_asset_paths.append({'image': local_image_path, 'audio': local_audio_path})

    # --- ขั้นตอนตัดต่อ ---
    print(f"  - Assembling video for project {doc_id}...")
    final_clips_list = []
    for asset in local_asset_paths:
        try:
            audio_clip = AudioFileClip(asset['audio'])
            image_clip = ImageClip(asset['image']).set_duration(audio_clip.duration)
            video_sub_clip = image_clip.set_audio(audio_clip)
            video_sub_clip.fps = 24
            final_clips_list.append(video_sub_clip)
        except Exception as e:
            print(f"    - ❌ Error creating sub-clip: {e}")

    # --- ขั้นตอน Render และอัปโหลด ---
    if final_clips_list:
        try:
            final_video_local_path = os.path.join(TEMP_FOLDER, f"{doc_id}_final_video.mp4")
            destination_blob_name = f"{doc_id}/final_video.mp4" # <--- ชื่อไฟล์บน GCS

            final_video = concatenate_videoclips(final_clips_list, method="compose")
            final_video.write_videofile(final_video_local_path, codec="libx264", audio_codec="aac")
            
            print(f"  - Uploading final video to {destination_blob_name}...")
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(final_video_local_path)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1), # กำหนดวันหมดอายุ
                method="GET", # อนุญาตให้ดาวน์โหลด (GET request)
            )
            print(f"  - Generated Signed URL (expires in 1 hour).")
            # ---------------------------
            db.collection('projects').document(doc_id).update({
                'status': 'completed',
                'final_video_url': signed_url, # <--- เก็บ Signed URL แทน Public URL
                'completed_at': firestore.SERVER_TIMESTAMP
            })
            print(f"  - ✅ Project {doc_id} completed!")

        

        except Exception as e:
            print(f"    - ❌ Error during final render/upload: {e}")
            db.collection('projects').document(doc_id).update({'status': 'compile_failed', 'error_message': str(e)})
    else:
        print(f"  - ❌ No clips to assemble. Marking as failed.")
        db.collection('projects').document(doc_id).update({'status': 'compile_failed', 'error_message': 'No clips were generated.'})

    # --- ขั้นตอนทำความสะอาด ---
    print(f"  - Cleaning up temporary files...")
    for asset in local_asset_paths:
        if os.path.exists(asset['image']): os.remove(asset['image'])
        if os.path.exists(asset['audio']): os.remove(asset['audio'])
    if 'final_video_local_path' in locals() and os.path.exists(final_video_local_path):
        os.remove(final_video_local_path)
    print(f"  - Cleanup complete.")

# --- 3. Main Loop ---
def main_loop():
    print("\n👂 Video Compiler is listening for projects with status 'compile_pending'...")
    while True:
        try:
            query = db.collection('projects').where('status', '==', 'compile_pending').limit(1)
            docs = query.stream()
            
            found_job = False
            for doc in docs:
                found_job = True
                doc_id = doc.id
                print(f"\n✨ Found a compile job! Project ID: {doc_id}")
                
                db.collection('projects').document(doc_id).update({'status': 'compiling'})
                process_compile_request(doc_id, doc.to_dict())
            
            if not found_job:
                print(".", end="", flush=True)
                time.sleep(10)
        except Exception as e:
            print(f"\n\n🚨 An critical error in video worker main loop: {e}\n\n")
            time.sleep(30)

if __name__ == "__main__":
    main_loop()