# =========================================
# APP_TEST.PY - BOT MONITOR LELANG (TEST MODE)
# =========================================
import requests, os
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

API_URL = "https://api.lelang.go.id/v1/auctions"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# =========================================
# HELPERS
# =========================================
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
    print(f"[{datetime.now()}] Bot TEST mulai jalan...")

    try:
        r = requests.get(API_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json().get("data", [])
    except Exception as e:
        print(f"[ERROR] Gagal ambil data dari API: {e}")
        return

    print(f"[INFO] Total {len(data)} lot ditemukan, semua akan dikirim (test mode)")
    for lot in data:
        send_message(lot)

    print(f"[{datetime.now()}] Bot TEST selesai cek.")

if __name__ == "__main__":
    main()
