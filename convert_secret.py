import json

# !!! แก้ไขตรงนี้ !!!
# ใส่ Path เต็มๆ ของไฟล์ Service Account Key .json ของคุณ
# ตัวอย่างสำหรับ Windows: "C:\\Users\\YourUser\\Downloads\\my-key.json"
# ตัวอย่างสำหรับ Mac/Linux: "/home/user/downloads/my-key.json"
# *** สำคัญ: ถ้าใน path มี \ ให้ใช้ \\ (backslash สองตัว) ***
path_to_your_key_file = "E:\\streamlit-story-app\\youtubeubload.json" # <--- แก้ไข Path นี้ให้ถูกต้อง

try:
    # เปิดไฟล์ JSON ต้นฉบับ
    with open(path_to_your_key_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # แปลง Python dictionary ให้กลายเป็น JSON String ที่ถูกต้องในบรรทัดเดียว
    json_string_for_toml = json.dumps(data)

    # พิมพ์ผลลัพธ์ออกมาเพื่อให้เราคัดลอก
    print("\n✅ คัดลอกข้อความทั้งหมดข้างล่างนี้ (รวมเครื่องหมาย \" ที่หัวและท้าย) ไปวางใน secrets.toml ได้เลย:\n")
    print("credentials_json = " + json_string_for_toml)
    print("\n")

except FileNotFoundError:
    print(f"❌ ไม่พบไฟล์ที่: {path_to_your_key_file}")
    print("กรุณาตรวจสอบ Path ของไฟล์ Service Account Key .json ของคุณให้ถูกต้อง")
except json.JSONDecodeError:
    print("❌ ไฟล์ .json ของคุณมีรูปแบบที่ไม่ถูกต้อง ไม่สามารถอ่านได้")
except Exception as e:
    print(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")