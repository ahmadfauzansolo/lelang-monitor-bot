# =========================================
# APP.PY - BOT MONITOR LELANG (FINAL)
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
    """Ubah ISO date ke format lebih manusiawi"""
    try:
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y")
    except Exception:
        return d[:10] if d else "-"

# =========================================
# TELEGRAM
# =========================================
def send_message(lot):
    """Kirim notifikasi lot ke Telegram, dengan minimal 1 foto"""
    lot_id = str(lot.get("id"))
    title = lot.get("title", "(tanpa judul)")
    lokasi = lot.get("city", "(tidak diketahui)")
    instansi = lot.get("office", {}).get("name", "(tidak diketahui)")
    penjual = lot.get("seller", {}).get("name", "(tidak diketahui)")

    tgl_mulai = format_date(lot.get("startDate"))
    tgl_selesai = format_date(lot.get("auctionDate"))
    harga = int(lot.get("price", 0))

    link = f"https://lelang.go.id/kpknl/{lot.get('officeId')}/detail-auction/{lot_id}"

    caption = (
        f"🔔 <b>{title}</b>\n"
        f"📍 Lokasi: {lokasi}\n"
        f"🏢 Instansi: {instansi}\n"
        f"👤 Penjual: {penjual}\n"
        f"🗓 {tgl_mulai} → {tgl_selesai}\n"
        f"💰 Nilai limit: Rp {harga:,}\n"
        f"🔗 <a href='{link}'>Lihat detail lelang</a>"
    )

    photos = lot.get("photos", [])
    photo_url = None
    if photos:
        p = photos[0]
        file_url = p.get("file", {}).get("fileUrl") if isinstance(p, dict) else None
        if file_url:
            # API kadang relatif → tambahkan domain
            if file_url.startswith("http"):
                photo_url = file_url
            else:
                photo_url = f"https://api.lelang.go.id{file_url}"

    # Kirim dengan foto kalau ada
    if photo_url:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "HTML",
            },
        )
        print(f"[DEBUG] Telegram resp: {resp.status_code} {resp.text}")
        if resp.status_code == 200:
            print(f"[INFO] Lot {lot_id} terkirim dengan foto")
        else:
            print(f"[ERROR] Lot {lot_id} gagal kirim foto")
    else:
        # fallback: teks saja
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": caption,
                "parse_mode": "HTML",
            },
        )
        print(f"[DEBUG] Telegram resp: {resp.status_code} {resp.text}")
        if resp.status_code == 200:
            print(f"[INFO] Lot {lot_id} terkirim tanpa foto")
        else:
            print(f"[ERROR] Lot {lot_id} gagal kirim pesan")

# =========================================
# MAIN
# =========================================
def main():
    print(f"[{datetime.now()}] Bot mulai jalan...")

    try:
        r = requests.get(API_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json().get("data", [])
        print(f"[INFO] Ditemukan {len(data)} lot di API")
    except Exception as e:
        print(f"[ERROR] Gagal ambil data dari API: {e}")
        return

    for lot in data:
        send_message(lot)

    print(f"[{datetime.now()}] Bot selesai kirim semua lot.")

if __name__ == "__main__":
    main()
