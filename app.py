# =========================================
# APP.PY - BOT MONITOR LELANG (FINAL UPDATED)
# =========================================
import requests, json, os
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

API_URL = "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
DETAIL_URL = "https://api.lelang.go.id/api/v1/landing-page/info/{}"
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

def fetch_detail(lot_id):
    try:
        r = requests.get(DETAIL_URL.format(lot_id), timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json().get("data", {})
        return data
    except Exception as e:
        print(f"[ERROR] Gagal ambil detail lot {lot_id}: {e}")
        return None

# =========================================
# TELEGRAM
# =========================================
def send_message(lot, detail):
    lot_id = lot.get("lotLelangId") or lot.get("id")
    title = lot.get("namaLotLelang") or detail.get("namaLotLelang") or "(tanpa judul)"
    lokasi = lot.get("namaLokasi") or detail.get("namaLokasi") or "(tidak diketahui)"
    instansi = lot.get("namaUnitKerja") or detail.get("namaUnitKerja") or "(tidak diketahui)"
    start = format_date(lot.get("tglMulaiLelang") or detail.get("tglMulaiLelang", ""))
    end = format_date(lot.get("tglSelesaiLelang") or detail.get("tglSelesaiLelang", ""))
    nilai_limit = int(lot.get("nilaiLimit") or detail.get("nilaiLimit", 0))
    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId') or detail.get('unitKerjaId')}/detail-auction/{lot_id}"

    # Cara penawaran
    cara_penawaran = detail.get("caraPenawaran", "(tidak diketahui)")

    # Uraian barang
    barangs = detail.get("content", {}).get("barangs", [])
    uraian_list = []
    for b in barangs:
        uraian_list.append(
            f"- {b.get('nama','')} ({b.get('tahun','')}, {b.get('warna','')}, {b.get('nopol','')})\n"
            f"  Alamat: {b.get('alamat','')}\n"
            f"  Bukti kepemilikan: {b.get('buktiKepemilikan','')} {b.get('buktiKepemilikanNo','')}"
        )
    uraian = "\n".join(uraian_list) if uraian_list else "-"

    # Penjual
    seller = detail.get("content", {}).get("seller", {})
    penjual = seller.get("namaPenjual") or seller.get("namaOrganisasiPenjual") or "(tidak diketahui)"
    telepon_penjual = seller.get("nomorTelepon", "")
    alamat_penjual = seller.get("alamat", "")
    kota_penjual = seller.get("namaKota", "")
    prov_penjual = seller.get("namaProvinsi", "")

    # Organizer
    organizer = detail.get("content", {}).get("organizer", {})
    organizer_info = f"{organizer.get('namaUnitKerja','')} - {organizer.get('namaBank','')}"

    # Jumlah view
    views = detail.get("views", 0)

    caption = (
        f"{title}\n"
        f"📍 Lokasi: {lokasi}\n"
        f"🏢 Instansi: {instansi}\n"
        f"👤 Penjual: {penjual}\n"
        f"   📞 {telepon_penjual}\n"
        f"   🏠 {alamat_penjual}, {kota_penjual}, {prov_penjual}\n"
        f"🗓 {start} → {end}\n"
        f"💰 Nilai limit: Rp {nilai_limit:,}\n"
        f"⚖️ Cara penawaran: {cara_penawaran}\n"
        f"📦 Barang:\n{uraian}\n"
        f"🏦 Organizer: {organizer_info}\n"
        f"👁️ Dilihat: {views}\n"
        f"🔗 <a href='{link}'>Lihat detail lelang</a>"
    )

    # ambil foto minimal 1
    photos = detail.get("photos", [])
    if photos:
        photo_url = photos[0].get("file", {}).get("fileUrl") or photos[0].get("fileUrl")
        if photo_url and not photo_url.startswith("http"):
            photo_url = f"https://file.lelang.go.id{photo_url}"
        try:
            img = requests.get(photo_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if img.status_code == 200:
                files = {"photo": ("img.jpg", img.content)}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
                res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data=data, files=files)
                print(f"[INFO] Lot {lot_id} terkirim dengan foto, status {res.status_code}")
                return True
        except Exception as e:
            print(f"[ERROR] Gagal kirim foto lot {lot_id}: {e}")

    # fallback tanpa foto
    res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"})
    print(f"[INFO] Lot {lot_id} terkirim tanpa foto, status {res.status_code}")
    return False

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

        detail = fetch_detail(lot_id)
        if not detail:
            continue

        send_message(lot, detail)
        seen.add(lot_id)
        new_count += 1

    save_seen(seen)
    print(f"[INFO] {new_count} lot baru terkirim")
    print(f"[{datetime.now()}] Bot selesai kirim semua lot.")

if __name__ == "__main__":
    main()
