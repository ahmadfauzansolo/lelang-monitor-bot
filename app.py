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
        return d[:10] if d else "-"

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

    caption = (
        f"🔔 <b>{title}</b>\n"
        f"📍 Lokasi: {lokasi}\n"
        f"🏢 Instansi: {instansi}\n"
        f"🗓 {start} → {end}\n"
        f"💰 Nilai limit: Rp {nilai_limit:,}\n"
        f"💵 Uang jaminan: Rp {uang_jaminan:,}\n"
        f"🔗 <a href='{link}'>Lihat detail lelang</a>"
    )

    photos = []
    # beberapa lot pakai "photos", kadang "gambar", kadang "foto"
    if "photos" in lot:
        photos = lot["photos"]
    elif "gambar" in lot:
        photos = lot["gambar"]
    elif "foto" in lot:
        photos = lot["foto"]

    if not photos:
        # fallback teks kalau ga ada foto
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"},
        )
        return

    # 🔹 coba kirim album via URL langsung
    media = []
    for i, p in enumerate(photos):
        file_url = (
            p.get("file", {}).get("fileUrl")
            or p.get("fileUrl")
            or p.get("url")
        )
        if not file_url:
            continue
        if not file_url.startswith("http"):
            file_url = f"https://api.lelang.go.id{file_url}"
        media.append({
            "type": "photo",
            "media": file_url,
            "caption": caption if i == 0 else "",
            "parse_mode": "HTML"
        })

    if not media:
        print("[WARN] Tidak ada URL foto yang valid")
        return

    res = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup",
        json={"chat_id": TELEGRAM_CHAT_ID, "media": media}
    )

    if res.status_code == 200:
        print(f"[INFO] Album berhasil dikirim ({len(media)} foto)")
        return True
    else:
        print(f"[WARN] Gagal album via URL: {res.text}, coba upload manual...")

        # 🔹 fallback: upload foto satu-satu
        for i, m in enumerate(media):
            try:
                img = requests.get(m["media"], timeout=10)
                if img.status_code == 200:
                    files = {"photo": ("img.jpg", img.content)}
                    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": m["caption"], "parse_mode": "HTML"}
                    ru = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data=data, files=files)
                    print(f"[INFO] Foto {i+1} upload status {ru.status_code}")
            except Exception as e:
                print(f"[ERROR] Foto {i+1} gagal: {e}")
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

            if data:
                print("===== SAMPLE JSON LOT =====")
                print(json.dumps(data[0], indent=2, ensure_ascii=False))
                print("===== END SAMPLE =====")

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
