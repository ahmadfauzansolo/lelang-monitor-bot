# =========================================
# APP.PY - BOT MONITOR LELANG FINAL (RAPIH)
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
def format_date(d: str) -> str:
    """Ubah ISO date ke format '12 Sep 2025'"""
    try:
        dt = datetime.fromisoformat(d.replace("Z", ""))
        return dt.strftime("%d %b %Y")
    except Exception:
        return d[:10] if d else "-"

# =========================================
# TELEGRAM
# =========================================
def send_message(lot):
    lot_id = lot.get("lotLelangId")
    title = lot.get("namaLotLelang", "(tanpa judul)")
    lokasi = lot.get("namaLokasi", "(tidak diketahui)")
    instansi = lot.get("namaUnitKerja", "(tidak diketahui)")
    penjual = lot.get("namaPenjual", "(tidak diketahui)")
    start = format_date(lot.get("tglMulaiLelang", "-"))
    end = format_date(lot.get("tglSelesaiLelang", "-"))
    harga = int(lot.get("nilaiLimit", 0))

    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot_id}"
    image_url = None
    if lot.get("fotoLotLelang"):
        # Ambil foto pertama
        image_url = lot["fotoLotLelang"][0]["url"]

    caption = (
        f"{title}\n"
        f"📍 Lokasi: {lokasi}\n"
        f"🏢 Instansi: {instansi}\n"
        f"👤 Penjual: {penjual}\n"
        f"🗓 {start} → {end}\n"
        f"💰 Nilai limit: Rp {harga:,}\n"
        f"🔗 <a href='{link}'>Lihat detail lelang</a>"
    )

    if image_url:
        ru = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML",
                "photo": image_url
            },
            timeout=20
        )
    else:
        ru = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": caption,
                "parse_mode": "HTML"
            },
            timeout=20
        )
    print(f"[INFO] Lot {lot_id} terkirim status {ru.status_code}")

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

    print(f"[INFO] Total {len(data)} lot ditemukan")

    for lot in data:
        send_message(lot)

    print(f"[{datetime.now()}] Bot selesai kirim semua lot.")

if __name__ == "__main__":
    main()
