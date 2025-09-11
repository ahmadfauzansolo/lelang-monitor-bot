from flask import Flask
import threading, time, requests, json
import os
from dotenv import load_dotenv

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

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
    return res.status_code == 200

# -----------------------------
# MONITOR FUNCTION
# -----------------------------
def monitor_lelang():
    seen = load_seen()
    print("✅ Monitor Lelang mulai. Instansi:", KEYWORD_INSTANSI)
    while True:
        try:
            r = requests.get(API_URL, timeout=20)
            data = r.json()
            items = data.get("data", []) or []
            for lot in items:
                lot_unique_id = f"{lot.get('unitKerjaId')}_{lot.get('lotLelangId')}"
                if not lot.get("id") or lot_unique_id in seen:
                    continue
                instansi = (lot.get("namaUnitKerja") or "").lower()
                if KEYWORD_INSTANSI not in instansi:
                    continue
                title = lot.get("namaLotLelang", "(tanpa judul)")
                start = lot.get("tglMulaiLelang", "")
                end = lot.get("tglSelesaiLelang", "")
                link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot.get('lotLelangId')}"
                text = f"🔔 <b>{title}</b>\nInstansi: {instansi}\n🗓 {start} → {end}\n🔗 {link}"
                if send_message(text):
                    print("✅ Terkirim:", lot_unique_id)
                else:
                    print("❌ Gagal kirim:", lot_unique_id)
                seen.add(lot_unique_id)
            save_seen(seen)
        except Exception as e:
            print("⚠ Error cek API:", e)
        time.sleep(CHECK_INTERVAL)

# -----------------------------
# START MONITOR DI THREAD TERPISAH
# -----------------------------
def start_monitor():
    t = threading.Thread(target=monitor_lelang)
    t.daemon = True
    t.start()

# -----------------------------
# FLASK ROUTE
# -----------------------------
@app.route("/")
def index():
    return "Bot Lelang Monitor aktif 🚀"

# -----------------------------
# RUN FLASK DI RENDER
# -----------------------------
if __name__ == "__main__":
    start_monitor()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
