from flask import Flask
import threading, time, requests, json
import os
from dotenv import load_dotenv
from datetime import datetime

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv()  # untuk local .env

app = Flask(__name__)

API_URL = "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
KEYWORD_INSTANSI = os.getenv("KEYWORD_INSTANSI", "KPKNL Surakarta").lower()
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "1800"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEEN_FILE = "seen_api.json"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# -----------------------------
# HELPERS
# -----------------------------
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(s):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(s), f, ensure_ascii=False, indent=2)

def format_date(d):
    try:
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y")
    except:
        return d[:10]

def send_message(lot):
    title = lot.get("namaLotLelang", "(tanpa judul)")
    instansi = lot.get("namaUnitKerja", "(tidak diketahui)")
    start = format_date(lot.get("tglMulaiLelang", ""))
    end = format_date(lot.get("tglSelesaiLelang", ""))
    lokasi = lot.get("namaLokasi", "(tidak diketahui)")
    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot.get('lotLelangId')}"

    # Ambil semua foto
    photos = lot.get("photos", [])
    media = []
    for i, p in enumerate(photos):
        file_url = p.get("file", {}).get("fileUrl")
        if not file_url:
            continue
        url = f"https://api.lelang.go.id{file_url}"
        if i == 0:
            caption = (
                f"🔔 <b>{title}</b>\n"
                f"📍 Lokasi: {lokasi}\n"
                f"🏢 Instansi: {instansi}\n"
                f"🗓 {start} → {end}\n"
                f"🔗 <a href='{link}'>Lihat detail lelang</a>"
            )
        else:
            caption = None
        media.append({"type": "photo", "media": url, "caption": caption, "parse_mode": "HTML"})

    if media:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "media": media})
        return res.status_code == 200
    else:
        text = (
            f"🔔 <b>{title}</b>\n"
            f"📍 Lokasi: {lokasi}\n"
            f"🏢 Instansi: {instansi}\n"
            f"🗓 {start} → {end}\n"
            f"🔗 <a href='{link}'>Lihat detail lelang</a>"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
        return res.status_code == 200

# -----------------------------
# MONITOR FUNCTION
# -----------------------------
def monitor_lelang():
    seen = load_seen()
    while True:
        try:
            resp = requests.get(API_URL)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for lot in data:
                    if KEYWORD_INSTANSI in lot.get("namaUnitKerja", "").lower():
                        lot_id = lot.get("id")
                        if lot_id not in seen:
                            if send_message(lot):
                                seen.add(lot_id)
                                save_seen(seen)
            else:
                print("Gagal fetch API:", resp.status_code)
        except Exception as e:
            print("Error:", e)
        time.sleep(CHECK_INTERVAL)

# -----------------------------
# FLASK ROUTE
# -----------------------------
@app.route("/")
def home():
    return "Bot Lelang Monitor aktif 🚀"

# -----------------------------
# START MONITOR THREAD
# -----------------------------
threading.Thread(target=monitor_lelang, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
