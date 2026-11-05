import os
import re
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from supabase import create_client, Client
from datetime import datetime, timedelta
import pytesseract
from PIL import Image

app = FastAPI(title="Taahhüt Takip Python Backend")

# Çevre Değişkenlerinden Supabase Bilgilerini Al
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Supabase İstemcisi
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_URL else None

@app.get("/")
def home():
    return {"message": "Taahhüt Takip OCR Servisi Çalışıyor!"}

# --- 1. OCR ENDPOINT: Fatura/Poliçe Fotoğrafından Bitiş Tarihi Okuma ---
@app.post("/api/ocr-scan")
async def scan_document(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        
        # Görselden metin çıkarma (Türkçe + İngilizce)
        text = pytesseract.image_to_string(image, lang='tur+eng')
        
        # Tarih formatlarını yakalama (DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD)
        date_pattern = r'\b(0[1-9]|[12][0-9]|3[01])[-/.](0[1-9]|1[012])[-/.](19|20)\d\d\b'
        matches = re.findall(date_pattern, text)
        
        found_dates = []
        if matches:
            for m in matches:
                # Bulunan tarihleri standart YYYY-MM-DD formatına dönüştür
                formatted_date = f"{m[2]}-{m[1]}-{m[0]}"
                if formatted_date not in found_dates:
                    found_dates.append(formatted_date)

        return {
            "success": True,
            "detected_dates": found_dates,
            "raw_text_snippet": text[:300]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 2. CRON SCRIPT: Bitiş Tarihi Yaklaşan Abonelikleri Tarama ---
@app.get("/api/cron/check-expirations")
async def check_expirations():
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase bağlantısı kurulmadı.")
        
    today = datetime.now().date()
    # 30 gün, 7 gün ve 1 gün kalan kayıtlar
    target_days = [30, 7, 1]
    expiring_items = []

    for days in target_days:
        target_date = (today + timedelta(days=days)).isoformat()
        res = supabase.table("subscriptions").select("*, profiles(email)").eq("end_date", target_date).execute()
        if res.data:
            for item in res.data:
                item["remaining_days"] = days
                expiring_items.append(item)

    return {
        "status": "success",
        "expiring_count": len(expiring_items),
        "items": expiring_items
    }