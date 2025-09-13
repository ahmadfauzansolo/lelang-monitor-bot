# =========================================
# APP.PY - BOT MONITOR LELANG (FINAL TANPA FILTER)
# =========================================
import requests, os
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

API_URL = "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# =========================================
# HELPERS
# =========================================
def format_date(d):
    """Format ISO date ke format '12 Sep 2025'"""
    try:
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y")
    except Exception:
        return d[:10] if d else "-"

# =========================================
# TELEGRAM
# =========================================
def send_message(lot):
    """Kirim notifikasi lot ke Telegram, dengan 1 foto utama kalau ada"""
    lot_id = str(lot.get("lotLelangId") or lot.get("id"))
    title = lot.get("namaLotLelang") or lot.get("title", "(tanpa judul)")
    lokasi = lot.get("namaLokasi") or lot.get("city", "(tidak diketahui)")
    instansi = lot.get("namaUnitKerja", "(tidak diketahui)")
    start = format_date(lot.get("tglMulaiLelang", ""))
    end = format_date(lot.get("tglSelesaiLelang", ""))
    harga = int(lot.get("nilaiLimit", lot.get("price", 0)))

    penjual = (
        lot.get("namaPenjual")
        or (lot.get("penjual", {}) or {}).get("nama")
        or "(tidak diketahui)"
    )

    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot_id}"

    caption = (
        f"🔔 <b>{title}</b>\n"
        f"📍 Lokasi: {lokasi}\n"
        f"🏢 Instansi: {instansi}\n"
        f"👤 Penjual: {penjual}\n"
        f"🗓 {start} → {end}\n"
        f"💰 Nilai limit: Rp {harga:,}\n"
        f"🔗 <a href='{link}'>Lihat detail lelang</a>"
    )

    # ambil minimal 1 foto kalau ada
    photos = lot.get("fotoLotLelang") or lot.get("photos") or []
    photo_url = None

    if photos and isinstance(photos, list):
        first = photos[0]
        if isinstance(first, dict):
            photo_url = (
                first.get("fileUrl")
                or (first.get("file", {}) or {}).get("fileUrl")
            )
        elif isinstance(first, str):
            photo_url = first

        if photo_url and not photo_url.startswith("http"):
            photo_url = "https://file.lelang.go.id" + photo_url

    # kirim ke Telegram
    if photo_url:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "HTML"
            },
        )
        print(f"[INFO] Lot {lot_id} terkirim dengan foto")
    else:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": caption,
                "parse_mode": "HTML"
            },
        )
        print(f"[INFO] Lot {lot_id} terkirim tanpa foto")

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
