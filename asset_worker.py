import os
import time
import io
from PIL import Image
from google.cloud import firestore, storage
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from google.cloud import texttospeech

# --- 1. การตั้งค่า ---
print("🚀 Starting Asset Production Worker (v2.0 - Organized)...")

# --- แก้ไขตรงนี้ ---
GCP_KEY_FILE_PATH = "E:\\streamlit-story-app\\youtubeubload.json"
GCP_PROJECT_ID = "youtubeubload"
GCP_LOCATION = "asia-southeast1"
BUCKET_NAME = "ai-story-factory-assets-nattapobiz" # <--- ชื่อ Bucket ของคุณ
# ------------------

# --- เพิ่มเข้ามา: จัดการโฟลเดอร์ไฟล์ชั่วคราว ---
TEMP_FOLDER = "temp_files"
if not os.path.exists(TEMP_FOLDER):
    os.makedirs(TEMP_FOLDER)
    print(f"Created temporary folder at: {TEMP_FOLDER}")
# ----------------------------------------------

try:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GCP_KEY_FILE_PATH
    db = firestore.Client(project=GCP_PROJECT_ID)
    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
    
    image_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
    tts_client = texttospeech.TextToSpeechClient()
    print("✅ Successfully connected to GCP services (Firestore, Storage, Vertex AI).")
except Exception as e:
    print(f"❌ Worker failed to initialize: {e}")
    exit()

# --- 2. ฟังก์ชันการทำงานของ Worker ---

def upload_to_gcs(file_path, destination_blob_name):
    """อัปโหลดไฟล์ไปยัง Google Cloud Storage"""
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(file_path)
    return blob.public_url

def process_asset_request(doc_id, doc_data):
    scenes = doc_data.get('scenes', [])
    updated_scenes = []
    
    for i, scene in enumerate(scenes):
        scene_num = i + 1
        print(f"  - Processing assets for scene {scene_num}/{len(scenes)}...")
        narration = scene.get("narration")
        image_prompt = scene.get("image_prompt")
        
        # --- แก้ไข Path ตรงนี้ ---
        image_path = os.path.join(TEMP_FOLDER, f"temp_image_{doc_id}_{scene_num}.png")
        audio_path = os.path.join(TEMP_FOLDER, f"temp_audio_{doc_id}_{scene_num}.mp3")
        # -------------------------
        
        try:
            # สร้างภาพ
            if image_prompt:
                print(f"    - Image creation for scene {scene_num}...")
                response_img = image_model.generate_images(prompt=image_prompt, number_of_images=1, aspect_ratio="16:9")
                response_img.images[0].save(location=image_path)
                image_url = upload_to_gcs(image_path, f"{doc_id}/scene_{scene_num}.png")
                os.remove(image_path)
                scene['image_url'] = image_url
                print(f"    - Image for scene {scene_num} created and uploaded.")
            else:
                scene['image_url'] = None
            
            # สร้างเสียง
            if narration:
                print(f"    - Audio creation for scene {scene_num}...")
                s_input = texttospeech.SynthesisInput(text=narration)
                voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Neural2-J")
                a_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
                response_tts = tts_client.synthesize_speech(input=s_input, voice=voice, audio_config=a_config)
                with open(audio_path, "wb") as out:
                    out.write(response_tts.audio_content)
                audio_url = upload_to_gcs(audio_path, f"{doc_id}/scene_{scene_num}.mp3")
                os.remove(audio_path)
                scene['audio_url'] = audio_url
                print(f"    - Audio for scene {scene_num} created and uploaded.")
            else:
                scene['audio_url'] = None
                
        except Exception as e:
            print(f"    - ❌ An error occurred during asset creation for scene {scene_num}: {e}")
            scene['error'] = str(e)
            
        updated_scenes.append(scene)

    # อัปเดต Firestore ด้วยข้อมูลใหม่ทั้งหมด
    print(f"  - Updating Firestore for project {doc_id}...")
    db.collection('projects').document(doc_id).update({
        'scenes': updated_scenes,
        'status': 'compile_pending',
        'assets_completed_at': firestore.SERVER_TIMESTAMP
    })
    print(f"  - ✅ Project {doc_id} asset production completed.")


# --- 3. Main Loop ---
def main_loop():
    print("\n👂 Asset Worker is listening for projects with status 'assets_pending'...")
    while True:
        try:
            query = db.collection('projects').where('status', '==', 'assets_pending').limit(1)
            docs = query.stream()
            
            found_job = False
            for doc in docs:
                found_job = True
                doc_id = doc.id
                print(f"\n✨ Found an asset job! Project ID: {doc_id}")
                
                db.collection('projects').document(doc_id).update({'status': 'assets_processing'})
                process_asset_request(doc_id, doc.to_dict())
            
            if not found_job:
                print(".", end="", flush=True)
                time.sleep(10)
        except Exception as e:
            print(f"\n\n🚨 An critical error in asset worker main loop: {e}\n\n")
            time.sleep(30)

if __name__ == "__main__":
    main_loop()