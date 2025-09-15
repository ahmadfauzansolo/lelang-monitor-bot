# =========================================
# APP.PY - BOT MONITOR LELANG (DEBUG DETAIL)
# =========================================
import requests, json, os
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

API_URL = "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
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
        return dt.strftime("%d %b %Y %H:%M")
    except Exception:
        return d[:10] if d else "-"

# =========================================
# TELEGRAM
# =========================================
def send_message(lot):
    lot_id = lot.get("lotLelangId") or lot.get("id")
    if not lot_id:
        return False

    # --- Ambil detail lot ---
    try:
        detail_url = f"https://api.lelang.go.id/api/v1/detail-lot-lelang/{lot_id}"
        detail_resp = requests.get(detail_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        detail = detail_resp.json().get("data", {})
        print(f"\n[DEBUG] Detail lot {lot_id}:")
        print(json.dumps(detail, indent=2, ensure_ascii=False))  # print JSON lengkap
    except Exception as e:
        print(f"[ERROR] Gagal ambil detail lot {lot_id}: {e}")
        detail = {}

    # --- Data dasar ---
    title = lot.get("namaLotLelang", "(tanpa judul)")
    lokasi = lot.get("namaLokasi", "(tidak diketahui)")
    instansi = lot.get("namaUnitKerja", "(tidak diketahui)")
    penjual = detail.get("namaPenjual") or lot.get("namaPenjual", "(tidak diketahui)")
    start = format_date(lot.get("tglMulaiLelang", ""))
    end = format_date(lot.get("tglSelesaiLelang", ""))
    nilai_limit = int(lot.get("nilaiLimit", 0))

    # --- Data tambahan dari detail (sementara pakai default dulu) ---
    uang_jaminan = int(detail.get("uangJaminan", 0))
    cara_penawaran = detail.get("caraPenawaran", "-")
    kode_lot = detail.get("kodeLotLelang", "-")
    batas_setor = format_date(detail.get("batasAkhirSetorUangJaminan", ""))

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

    # --- Kirim ke Telegram ---
    res = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"}
    )
    print(f"[INFO] Lot {lot_id} terkirim ke Telegram, status {res.status_code}")
    return True

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

    seen = load_seen()
    new_count = 0

    for lot in data:
        lot_id = lot.get("lotLelangId") or lot.get("id")
        if not lot_id or lot_id in seen:
            continue

        send_message(lot)
        seen.add(lot_id)
        new_count += 1

    save_seen(seen)
    print(f"[INFO] {new_count} lot baru terkirim")
    print(f"[{datetime.now()}] Bot selesai kirim semua lot.")

if __name__ == "__main__":
    main()
