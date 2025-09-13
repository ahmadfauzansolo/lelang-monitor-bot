# =========================================
# APP.PY - BOT MONITOR LELANG (CRON MODE - FIX)
# =========================================
# Fitur:
# - Monitor lot lelang dari API lelang.go.id
# - Kirim notifikasi ke Telegram jika ada lot baru
# - Menampilkan semua foto lot (album Telegram)
# - Menampilkan nilai limit dan uang jaminan
# - Mencegah duplikat via seen_api.json
# - Log info tiap step
# =========================================

import requests, json, os
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

API_URL = "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
KEYWORD_INSTANSI = os.getenv("KEYWORD_INSTANSI", "KPKNL Surakarta").lower()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEEN_FILE = "seen_api.json"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# =========================================
# HELPERS
# =========================================
def load_seen():
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
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
        print(f"[INFO] Disimpan {len(seen)} lot ke seen_api.json")
    except Exception as e:
        print(f"[ERROR] Gagal simpan seen_api.json: {e}")

def format_date(d):
    try:
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y")
    except Exception:
        return d[:10]

# =========================================
# TELEGRAM
# =========================================
def send_message(lot):
    """Kirim notifikasi lot ke Telegram, termasuk semua foto"""
    title = lot.get("namaLotLelang", "(tanpa judul)")
    instansi = lot.get("namaUnitKerja", "(tidak diketahui)")
    start = format_date(lot.get("tglMulaiLelang", ""))
    end = format_date(lot.get("tglSelesaiLelang", ""))
    lokasi = lot.get("namaLokasi", "(tidak diketahui)")
    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot.get('lotLelangId')}"

    nilai_limit = int(lot.get("nilaiLimit", 0))
    uang_jaminan = int(lot.get("uangJaminan", 0))

    photos = lot.get("photos", [])
    media = []

    for i, p in enumerate(photos):
        file_url = p.get("file", {}).get("fileUrl")
        if not file_url:
            continue
        url = f"https://api.lelang.go.id{file_url}"

        if i == 0:  # hanya foto pertama yang ada caption
            caption = (
                f"🔔 <b>{title}</b>\n"
                f"📍 Lokasi: {lokasi}\n"
                f"🏢 Instansi: {instansi}\n"
                f"🗓 {start} → {end}\n"
                f"💰 Nilai limit: Rp {nilai_limit:,}\n"
                f"💵 Uang jaminan: Rp {uang_jaminan:,}\n"
                f"🔗 <a href='{link}'>Lihat detail lelang</a>"
            )
            media.append({"type": "photo", "media": url, "caption": caption, "parse_mode": "HTML"})
        else:
            media.append({"type": "photo", "media": url})

    try:
        if media:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
            res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "media": media})
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
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})

        if res.status_code == 200:
            print(f"[INFO] Lot '{title}' berhasil dikirim ke Telegram")
            return True
        else:
            print(f"[ERROR] Gagal kirim ke Telegram: {res.status_code}, {res.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Exception kirim Telegram: {e}")
        return False

# =========================================
# MAIN FUNCTION
# =========================================
def monitor_lelang():
    seen = load_seen()
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
                        print(f"[INFO] Lot baru: {lot.get('namaLotLelang')}")
                        if send_message(lot):
                            seen.add(lot_id)
                            save_seen(seen)
                    else:
                        print(f"[INFO] Sudah ada: {lot.get('namaLotLelang')}")
        else:
            print(f"[ERROR] Gagal fetch API: {resp.status_code}")
    except Exception as e:
        print(f"[ERROR] Exception monitor_lelang: {e}")

# =========================================
# ENTRY POINT
# =========================================
if __name__ == "__main__":
    monitor_lelang()
