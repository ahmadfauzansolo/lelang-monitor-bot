# =========================================
# APP.PY - BOT MONITOR LELANG (CRON MODE)
# =========================================
import requests, json, os
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

API_URL = "https://api.lelang.go.id/v1/auctions"
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
        return d[:10] if d else "-"

# =========================================
# TELEGRAM
# =========================================
def send_message(lot):
    """Kirim notifikasi lot ke Telegram, termasuk semua foto via URL publik"""
    lot_id = str(lot.get("id"))
    title = lot.get("title", "(tanpa judul)")
    lokasi = lot.get("city", "(tidak diketahui)")
    tgl = lot.get("auctionDate", "-")
    harga = int(lot.get("price", 0))

    link = f"https://www.lelang.go.id/lot/{lot_id}"

    caption = (
        f"🔔 <b>{title}</b>\n"
        f"📍 Lokasi: {lokasi}\n"
        f"🗓 Tanggal lelang: {tgl}\n"
        f"💰 Harga awal: Rp {harga:,}\n"
        f"🔗 <a href='{link}'>Lihat detail lelang</a>"
    )

    photos = lot.get("photos", [])

    if not photos:
        # fallback teks kalau ga ada foto
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"},
        )
        print(f"[INFO] Lot {lot_id} terkirim tanpa foto")
        return

    # kirim foto pertama dengan caption
    first_url = photos[0].get("file", {}).get("fileUrl") if isinstance(photos[0], dict) else None
    if first_url and not first_url.startswith("http"):
        first_url = f"https://file.lelang.go.id{first_url}"

    if first_url:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID, "photo": first_url, "caption": caption, "parse_mode": "HTML"},
        )
        print(f"[INFO] Lot {lot_id} terkirim dengan foto pertama")

    # kirim foto sisanya tanpa caption
    for p in photos[1:]:
        file_url = p.get("file", {}).get("fileUrl") if isinstance(p, dict) else None
        if file_url and not file_url.startswith("http"):
            file_url = f"https://file.lelang.go.id{file_url}"
        if file_url:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                data={"chat_id": TELEGRAM_CHAT_ID, "photo": file_url},
            )

# =========================================
# MAIN
# =========================================
def main():
    print(f"[{datetime.now()}] Bot mulai jalan...")

    try:
        r = requests.get(API_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json().get("data", [])
    except Exception as e:
        print(f"[ERROR] Gagal ambil data dari API: {e}")
        return

    seen = load_seen()

    new_count = 0
    for lot in data:
        lot_id = str(lot.get("id"))
        if not lot_id or lot_id in seen:
            continue

        send_message(lot)
        seen.add(lot_id)
        new_count += 1

    save_seen(seen)
    print(f"[INFO] {new_count} lot baru terkirim")
    print(f"[{datetime.now()}] Bot selesai cek.")

if __name__ == "__main__":
    main()
