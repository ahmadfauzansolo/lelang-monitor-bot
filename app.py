# =========================================
# APP.PY - BOT MONITOR LELANG
# =========================================
# Fitur:
# - Monitor lot lelang dari API lelang.go.id
# - Kirim notifikasi ke Telegram jika ada lot baru
# - Menampilkan semua foto lot (album Telegram)
# - Menampilkan nilai limit dan uang jaminan
# - Mencegah duplikat via seen_api.json
# - Log info tiap step
# =========================================

from flask import Flask
import threading, time, requests, json, os
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENVIRONMENT VARIABLES
# =========================================
load_dotenv()  # load .env lokal (untuk testing)

app = Flask(__name__)

# URL API untuk kategori Mobil & Motor
API_URL = "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"

# Nama instansi yang dipantau (default: KPKNL Surakarta)
KEYWORD_INSTANSI = os.getenv("KEYWORD_INSTANSI", "KPKNL Surakarta").lower()

# Interval pengecekan dalam detik (default: 1800 detik = 30 menit)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "1800"))

# Token & chat_id Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# File untuk menyimpan lot yang sudah dikirim
SEEN_FILE = "seen_api.json"

# Validasi env
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# =========================================
# HELPERS
# =========================================
def load_seen():
    """Load lot yang sudah dikirim dari seen_api.json"""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            seen = set(json.load(f))
        print(f"[INFO] Loaded {len(seen)} lot dari seen_api.json")
        return seen
    except FileNotFoundError:
        print("[INFO] seen_api.json tidak ditemukan, membuat baru")
        return set()
    except Exception as e:
        print(f"[ERROR] Gagal load seen_api.json: {e}")
        return set()

def save_seen(seen):
    """Simpan lot yang sudah dikirim ke seen_api.json"""
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
        print(f"[INFO] Disimpan {len(seen)} lot ke seen_api.json")
    except Exception as e:
        print(f"[ERROR] Gagal simpan seen_api.json: {e}")

def format_date(d):
    """Format tanggal ISO ke dd MMM yyyy"""
    try:
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y")
    except Exception:
        return d[:10]

# =========================================
# TELEGRAM NOTIFICATION
# =========================================
def send_message(lot):
    """Kirim notifikasi lot ke Telegram, termasuk semua foto"""
    title = lot.get("namaLotLelang", "(tanpa judul)")
    instansi = lot.get("namaUnitKerja", "(tidak diketahui)")
    start = format_date(lot.get("tglMulaiLelang", ""))
    end = format_date(lot.get("tglSelesaiLelang", ""))
    lokasi = lot.get("namaLokasi", "(tidak diketahui)")
    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot.get('lotLelangId')}"

    # Nilai limit & uang jaminan
    nilai_limit = int(lot.get("nilaiLimit", 0))
    uang_jaminan = int(lot.get("uangJaminan", 0))

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
                f"💰 Nilai limit: Rp {nilai_limit:,}\n"
                f"💵 Uang jaminan: Rp {uang_jaminan:,}\n"
                f"🔗 <a href='{link}'>Lihat detail lelang</a>"
            )
        else:
            caption = None
        media.append({"type": "photo", "media": url, "caption": caption, "parse_mode": "HTML"})

    # Kirim media group jika ada foto, kalau tidak kirim text biasa
    if media:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
            res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "media": media})
            if res.status_code == 200:
                print(f"[INFO] Lot '{title}' dikirim ke Telegram ({len(media)} foto)")
                return True
            else:
                print(f"[ERROR] Gagal kirim media, status_code={res.status_code}, response={res.text}")
                return False
        except Exception as e:
            print(f"[ERROR] Exception kirim media: {e}")
            return False
    else:
        text = (
            f"🔔 <b>{title}</b>\n"
            f"📍 Lokasi: {lokasi}\n"
            f"🏢 Instansi: {instansi}\n"
            f"🗓 {start} → {end}\n"
            f"💰 Nilai limit: Rp {nilai_limit:,}\n"
            f"💵 Uang jaminan: Rp {uang_jaminan:,}\n"
            f"🔗 <a href='{link}'>Lihat detail lelang</a>"
        )
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
            if res.status_code == 200:
                print(f"[INFO] Lot '{title}' dikirim ke Telegram (text saja)")
                return True
            else:
                print(f"[ERROR] Gagal kirim text, status_code={res.status_code}, response={res.text}")
                return False
        except Exception as e:
            print(f"[ERROR] Exception kirim text: {e}")
            return False

# =========================================
# MONITOR LELANG FUNCTION
# =========================================
def monitor_lelang():
    """Thread utama untuk monitor API lelang"""
    seen = load_seen()
    while True:
        print("[INFO] Mulai cek API...")
        try:
            resp = requests.get(API_URL)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                print(f"[INFO] Ditemukan {len(data)} lot di API")
                for lot in data:
                    if KEYWORD_INSTANSI in lot.get("namaUnitKerja", "").lower():
                        lot_id = lot.get("id")
                        if lot_id not in seen:
                            print(f"[INFO] Lot baru ditemukan: {lot.get('namaLotLelang')}")
                            if send_message(lot):
                                seen.add(lot_id)
                                save_seen(seen)
                        else:
                            print(f"[INFO] Lot sudah dikirim sebelumnya: {lot.get('namaLotLelang')}")
            else:
                print(f"[ERROR] Gagal fetch API: status_code={resp.status_code}")
        except Exception as e:
            print(f"[ERROR] Exception monitor_lelang: {e}")
        print(f"[INFO] Sleep {CHECK_INTERVAL} detik sebelum cek lagi\n")
        time.sleep(CHECK_INTERVAL)

# =========================================
# FLASK ROUTE
# =========================================
@app.route("/")
def home():
    return "Bot Lelang Monitor aktif 🚀"

# =========================================
# START MONITOR THREAD
# =========================================
threading.Thread(target=monitor_lelang, daemon=True).start()

# =========================================
# RUN FLASK
# =========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
