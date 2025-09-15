# =========================================
# APP.PY - BOT MONITOR LELANG (FINAL FIX)
# =========================================
import requests, json, os, logging
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# CONFIG
# =========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEEN_FILE = "seen_api.json"

API_KATALOG = "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
API_DETAIL = "https://api.lelang.go.id/api/v1/lot-lelang/{}"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
)

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di .env!")

# =========================================
# HELPERS
# =========================================
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()
    except Exception as e:
        logging.error(f"Gagal load seen file: {e}")
        return set()

def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Gagal simpan seen file: {e}")

def format_date(d):
    try:
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y %H:%M")
    except Exception:
        return d if d else "-"

# =========================================
# FETCH DETAIL LOT
# =========================================
def fetch_detail(lot_id):
    url = API_DETAIL.format(lot_id)
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        return data.get("data", {})
    except Exception as e:
        logging.error(f"Gagal fetch detail lot {lot_id}: {e}")
        return {}

# =========================================
# TELEGRAM
# =========================================
def send_message(lot, detail):
    lot_id = lot.get("lotLelangId") or lot.get("id")
    title = lot.get("namaLotLelang", "(tanpa judul)")
    lokasi = lot.get("namaLokasi", "(tidak diketahui)")
    instansi = lot.get("namaUnitKerja", "(tidak diketahui)")
    penjual = lot.get("namaPenjual", "(tidak diketahui)")
    start = format_date(lot.get("tglMulaiLelang", ""))
    end = format_date(lot.get("tglSelesaiLelang", ""))
    nilai_limit = int(lot.get("nilaiLimit", 0))

    # ambil dari detail
    uang_jaminan = int(detail.get("uangJaminan", 0))
    cara_penawaran = detail.get("jenisPenawaran", "-")
    kode_lot = detail.get("kodeLot", "-")
    batas_setor = format_date(detail.get("batasSetorUangJaminan"))

    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot_id}"

    caption = (
        f"{title}\n"
        f"📍 Lokasi: {lokasi}\n"
        f"🏢 Instansi: {instansi}\n"
        f"👤 Penjual: {penjual}\n"
        f"🗓 {start} → {end}\n"
        f"💰 Nilai limit: Rp {nilai_limit:,}\n"
        f"💵 Uang jaminan: Rp {uang_jaminan:,}\n"
        f"⚙️ Cara penawaran: {cara_penawaran}\n"
        f"🔑 Kode Lot: {kode_lot}\n"
        f"⏳ Batas setor jaminan: {batas_setor}\n"
        f"🔗 <a href='{link}'>Lihat detail lelang</a>"
    )

    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"}
        )
        logging.info(f"Lot {lot_id} terkirim ke Telegram, status {res.status_code}")
    except Exception as e:
        logging.error(f"Gagal kirim Telegram lot {lot_id}: {e}")

# =========================================
# MAIN
# =========================================
def main():
    logging.info("Bot mulai jalan...")
    try:
        r = requests.get(API_KATALOG, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json().get("data", [])
        logging.info(f"Ditemukan {len(data)} lot di API katalog")
    except Exception as e:
        logging.error(f"Gagal ambil data katalog: {e}")
        return

    seen = load_seen()
    new_count = 0

    for lot in data:
        lot_id = lot.get("lotLelangId") or lot.get("id")
        if not lot_id or lot_id in seen:
            continue

        detail = fetch_detail(lot_id)
        if not detail:
            logging.warning(f"Detail lot {lot_id} kosong!")
        send_message(lot, detail)

        seen.add(lot_id)
        new_count += 1

    save_seen(seen)
    logging.info(f"{new_count} lot baru terkirim")
    logging.info("Bot selesai kirim semua lot.")

if __name__ == "__main__":
    main()
