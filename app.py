# =========================================
# APP.PY - BOT MONITOR LELANG (FINAL - WITH DETAILED LOGGING)
# =========================================
# Perubahan: menambahkan logging detail pada:
#  - get_detail (attempts, status codes)
#  - send_to_telegram (download attempts, HTTP status, Telegram response)
#  - fallback flows (send by URL, send text)
# Semua parsing / formatting / struktur pesan tetap sesuai versi yang sudah disetujui.
# =========================================

import requests
import json
import os
import time
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

API_URL = (
    "https://api.lelang.go.id/api/v1/landing-page-kpknl/"
    "6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/"
    "katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
)
DETAIL_URL = "https://api.lelang.go.id/api/v1/landing-page/info/{}"  # {} = lotLelangId
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEEN_FILE = "seen_api.json"
BASE_PHOTO_URL = "https://file.lelang.go.id"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# =========================================
# SIMPLE LOGGING HELPERS (consistent format)
# =========================================
def log(level, msg):
    # level: INFO, WARN, ERROR, DEBUG
    print(f"[{datetime.now()}] [{level}] {msg}")

def short(text, n=300):
    t = str(text) or ""
    return t if len(t) <= n else t[:n] + "...(truncated)"

# =========================================
# HELPERS - file seen
# =========================================
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            seen_list = json.load(f)
            seen = set(seen_list)
        log("INFO", f"Loaded {len(seen)} lot dari {SEEN_FILE}")
        return seen
    except FileNotFoundError:
        log("INFO", f"{SEEN_FILE} tidak ditemukan, membuat baru")
        return set()
    except Exception as e:
        log("ERROR", f"Gagal load {SEEN_FILE}: {e}")
        return set()

def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
        log("INFO", f"Disimpan {len(seen)} lot ke {SEEN_FILE}")
    except Exception as e:
        log("ERROR", f"Gagal simpan {SEEN_FILE}: {e}")

# =========================================
# UTILITIES: formatting & safe-get
# =========================================
def format_date_iso(d, with_time=False):
    try:
        if not d:
            return "-"
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y %H:%M") if with_time else dt.strftime("%d %b %Y")
    except Exception:
        return d[:16] if d else "-"

def format_rupiah(v):
    try:
        if v is None or v == "":
            return "Rp -"
        n = int(float(str(v)))
        return f"Rp {n:,}"
    except Exception:
        return "Rp -"

def html_escape(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def first_non_empty(*args):
    for a in args:
        if a is None:
            continue
        if isinstance(a, str) and a.strip() == "":
            continue
        return a
    return None

# =========================================
# FETCH DETAIL with retries + logging
# =========================================
def get_detail(lot_id, retries=3, backoff=0.6):
    if not lot_id:
        return {}
    url = DETAIL_URL.format(lot_id)
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            log("DEBUG", f"Fetch detail attempt {attempt} for {lot_id} -> {url}")
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            log("DEBUG", f"Detail fetch status {r.status_code} for {lot_id}")
            if r.status_code == 200:
                try:
                    data = r.json().get("data", {}) or {}
                    log("INFO", f"Berhasil fetch detail {lot_id} (size: {len(json.dumps(data))} bytes)")
                    return data
                except Exception as e:
                    log("WARN", f"Parsing JSON detail {lot_id} gagal: {e} -- response snippet: {short(r.text)}")
                    return {}
            else:
                log("WARN", f"Fetch detail gagal {lot_id}, status {r.status_code} (attempt {attempt}) -- snippet: {short(r.text)}")
        except Exception as e:
            last_exc = e
            log("WARN", f"Exception fetch detail {lot_id} attempt {attempt}: {e}")
        time.sleep(backoff * attempt)
    if last_exc:
        log("ERROR", f"Semua percobaan fetch detail gagal untuk {lot_id}: {last_exc}")
    return {}

# =========================================
# PARSE DETAIL: robustly pick fields from possible locations
# =========================================
def parse_detail(detail):
    out = {
        "seller_name": None,
        "seller_phone": None,
        "seller_address": None,
        "seller_city": None,
        "seller_prov": None,
        "cara_penawaran": None,
        "uang_jaminan": None,
        "barangs": [],
        "organizer": {},
        "views": 0,
        "photos": [],
    }
    if not detail:
        return out

    content = detail.get("content", {}) or {}
    seller = content.get("seller") or detail.get("seller") or {}

    out["seller_name"] = first_non_empty(
        seller.get("namaOrganisasiPenjual"),
        seller.get("namaPenjual"),
        seller.get("nama_organisasi_penjual"),
        seller.get("nama"),
    ) or None

    out["seller_phone"] = first_non_empty(
        seller.get("nomorTelepon"),
        seller.get("nomor_telepon"),
        seller.get("telepon"),
        seller.get("nomor"),
    ) or None

    out["seller_address"] = first_non_empty(
        seller.get("alamat"),
        seller.get("address"),
    ) or None

    out["seller_city"] = first_non_empty(
        seller.get("namaKota"),
        seller.get("nama_kota"),
        seller.get("kota"),
    ) or None

    out["seller_prov"] = first_non_empty(
        seller.get("namaProvinsi"),
        seller.get("nama_provinsi"),
        seller.get("provinsi"),
    ) or None

    out["cara_penawaran"] = first_non_empty(
        detail.get("caraPenawaran"),
        content.get("caraPenawaran"),
        (content.get("lot") or {}).get("caraPenawaran"),
        detail.get("cara_penawaran"),
    ) or None

    out["uang_jaminan"] = first_non_empty(
        detail.get("uangJaminan"),
        detail.get("uang_jaminan"),
        content.get("uangJaminan"),
    )

    barangs = content.get("barangs")
    if not barangs:
        lot_block = content.get("lot") or {}
        barangs = lot_block.get("barang") or lot_block.get("barangs")
    if not barangs:
        barangs = detail.get("barangs") or []

    normalized = []
    for b in barangs or []:
        nm = first_non_empty(b.get("nama"), b.get("namaBarang"), b.get("nama_barang"))
        tahun = first_non_empty(b.get("tahun"), b.get("thn"), b.get("tahun_barang"))
        warna = first_non_empty(b.get("warna"), b.get("color"))
        nomor_rangka = first_non_empty(
            b.get("nomorRangka"), b.get("noRangka"), b.get("nomor_rangka"), b.get("noRangka")
        )
        nopol = first_non_empty(
            b.get("nopol"), b.get("nomorPolisi"), b.get("noPolisi"), b.get("nomor_polisi")
        )
        alamat_b = first_non_empty(b.get("alamat"), b.get("lokasi"), b.get("alamatBarang"))
        bukti = first_non_empty(b.get("buktiKepemilikan"), b.get("bukti_kepemilikan"))
        bukti_no = first_non_empty(
            b.get("buktiKepemilikanNo"), b.get("buktiKepemilikanNo"), b.get("bukti_kepemilikan_no")
        )
        stnk = first_non_empty(b.get("stnk"), b.get("stnk_no"))

        normalized.append(
            {
                "nama": nm or "-",
                "tahun": tahun or "-",
                "warna": warna or "-",
                "nomor_rangka": nomor_rangka or "-",
                "nopol": nopol or "-",
                "alamat": alamat_b or "-",
                "bukti": bukti or "-",
                "bukti_no": bukti_no or "-",
                "stnk": stnk or "-",
            }
        )
    out["barangs"] = normalized

    organizer = content.get("organizer") or detail.get("organizer") or {}
    out["organizer"] = {
        "namaUnitKerja": organizer.get("namaUnitKerja") or organizer.get("nama_unit_kerja") or organizer.get("namaUnit"),
        "namaBank": organizer.get("namaBank") or organizer.get("bank"),
        "nomorTelepon": organizer.get("nomorTelepon") or organizer.get("nomor_telepon") or organizer.get("telepon"),
        "alamat": organizer.get("alamat"),
    }

    out["views"] = first_non_empty(detail.get("views"), detail.get("jumlahView"), 0) or 0
    out["photos"] = detail.get("photos") or content.get("photos") or detail.get("photos", []) or []

    return out

# =========================================
# BUILD CAPTION / TEXT (all barang included)
# =========================================
def build_message_text(lot, detail_parsed):
    title = lot.get("namaLotLelang") or lot.get("namaLot") or "(tanpa judul)"
    lokasi = lot.get("namaLokasi") or lot.get("lokasi") or "-"
    instansi = lot.get("namaUnitKerja") or lot.get("namaUnit") or "-"
    start = format_date_iso(lot.get("tglMulaiLelang") or lot.get("tglMulai"), with_time=True)
    end = format_date_iso(lot.get("tglSelesaiLelang") or lot.get("tglSelesai"), with_time=True)

    seller_name = detail_parsed.get("seller_name") or "(tidak diketahui)"
    seller_phone = detail_parsed.get("seller_phone") or "-"
    seller_addr = detail_parsed.get("seller_address") or "-"
    seller_city = detail_parsed.get("seller_city") or "-"
    seller_prov = detail_parsed.get("seller_prov") or "-"

    nilai_limit = format_rupiah(first_non_empty(lot.get("nilaiLimit"), lot.get("nilai_limit"), None))
    uang_jaminan = format_rupiah(first_non_empty(detail_parsed.get("uang_jaminan"), detail_parsed.get("uang_jaminan"), lot.get("uangJaminan"), lot.get("uangJaminan")))

    cara = detail_parsed.get("cara_penawaran") or "-"
    if isinstance(cara, str):
        cara = cara.replace("_", " ").title()

    barang_lines = []
    for i, b in enumerate(detail_parsed.get("barangs", []) or [], start=1):
        nm = b.get("nama", "-")
        tahun = b.get("tahun", "-")
        warna = b.get("warna", "-")
        rangka = b.get("nomor_rangka", "-")
        nopol = b.get("nopol", "-")
        alamat_b = b.get("alamat", "-")
        bukti = b.get("bukti", "-")
        bukti_no = b.get("bukti_no", "-")
        stnk = b.get("stnk", "-")

        block = []
        summary = f"- {nm} ({tahun}, {warna})"
        detail_data = []
        if rangka and rangka != "-":
            detail_data.append(f"No. Rangka: {rangka}")
        if nopol and nopol != "-":
            detail_data.append(f"Nopol: {nopol}")
        if stnk and stnk != "-":
            detail_data.append(f"STNK: {stnk}")
        if detail_data:
            summary += " — " + " / ".join(detail_data)
        block.append(summary)
        if alamat_b and alamat_b != "-":
            block.append(f"  Alamat: {alamat_b}")
        if bukti and bukti != "-":
            if bukti_no and bukti_no != "-":
                block.append(f"  Bukti kepemilikan: {bukti} {bukti_no}")
            else:
                block.append(f"  Bukti kepemilikan: {bukti}")
        barang_lines.append("\n".join(block))

    barang_text = "\n".join(barang_lines) if barang_lines else "-"

    organizer = detail_parsed.get("organizer", {}) or {}
    organizer_info = f"{organizer.get('namaUnitKerja') or '-'} / {organizer.get('namaBank') or '-'}"

    views = detail_parsed.get("views") or 0

    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot.get('lotLelangId') or lot.get('id')}"

    pieces = []
    pieces.append(html_escape(title))
    pieces.append(f"📍 Lokasi: {html_escape(lokasi)}")
    pieces.append(f"🏢 Instansi: {html_escape(instansi)}")
    pieces.append(f"👤 Penjual: {html_escape(seller_name)}")
    pieces.append(f"   📞 {html_escape(seller_phone)}")
    pieces.append(f"   🏠 {html_escape(seller_addr)}, {html_escape(seller_city)}, {html_escape(seller_prov)}")
    pieces.append(f"🗓 {html_escape(start)} → {html_escape(end)}")
    pieces.append(f"💰 Nilai limit: {html_escape(nilai_limit)}")
    pieces.append(f"💵 Uang jaminan: {html_escape(uang_jaminan)}")
    pieces.append(f"⚖️ Cara penawaran: {html_escape(cara)}")
    pieces.append("📦 Barang:")
    if barang_text != "-":
        barang_blocks_escaped = []
        for blk in barang_lines:
            barang_blocks_escaped.append(html_escape(blk))
        pieces.append("\n".join(barang_blocks_escaped))
    else:
        pieces.append("-")
    pieces.append(f"🏦 Organizer: {html_escape(organizer_info)}")
    pieces.append(f"👁️ Dilihat: {html_escape(str(views))}")
    pieces.append(f"🔗 <a href='{html_escape(link)}'>Lihat detail lelang</a>")

    full_text = "\n".join(pieces)
    return full_text

# =========================================
# SEND to TELEGRAM (single cover photo preferred) with detailed logging
# =========================================
def send_to_telegram(full_text, photos):
    safe_caption_len = 800  # keep below Telegram caption limit and safe with HTML
    photo_item = None
    if photos:
        for p in photos:
            if p.get("iscover"):
                photo_item = p
                break
        if not photo_item:
            photo_item = photos[0]

    photo_url = None
    if photo_item:
        file_block = photo_item.get("file") or {}
        file_url = file_block.get("fileUrl") or photo_item.get("fileUrl")
        if file_url:
            photo_url = file_url if file_url.startswith("http") else BASE_PHOTO_URL + file_url
            log("DEBUG", f"Resolved photo_url: {photo_url}")

    caption_short = full_text
    if len(caption_short) > safe_caption_len:
        caption_short = caption_short[:safe_caption_len].rsplit("\n", 1)[0] + "\n\u2026"

    # 1) Try download with Referer header and upload to Telegram
    if photo_url:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://lelang.go.id/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        try:
            log("DEBUG", f"Attempting to download photo for upload: {photo_url}")
            img_resp = requests.get(photo_url, timeout=20, headers=headers)
            log("DEBUG", f"Download status: {img_resp.status_code} for {short(photo_url)}")
            if img_resp.status_code == 200 and img_resp.content:
                # verify minimal content
                if len(img_resp.content) < 500:
                    log("WARN", f"Downloaded image seems small ({len(img_resp.content)} bytes) - might be HTML error page")
                files = {"photo": ("img.jpg", img_resp.content)}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption_short, "parse_mode": "HTML"}
                try:
                    r = requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                        data=data,
                        files=files,
                        timeout=30,
                    )
                    log("DEBUG", f"Telegram upload response: {r.status_code} - {short(r.text)}")
                    if r.status_code in (200, 201):
                        log("INFO", f"Photo uploaded & sent via Telegram (upload) successfully")
                        # if caption truncated, send full message separately
                        if caption_short != full_text:
                            time.sleep(0.4)
                            send_message_text(full_text)
                        return True
                    else:
                        log("WARN", f"sendPhoto (upload) returned {r.status_code} - {short(r.text)}")
                except Exception as e:
                    log("WARN", f"Exception during upload-to-telegram: {e}")
            else:
                log("WARN", f"Gagal download photo {photo_url}, status {img_resp.status_code} (will try fallback)")
        except Exception as e:
            log("WARN", f"Exception saat download photo {photo_url}: {e}")

        # 2) Fallback: let Telegram fetch photo by URL
        try:
            log("DEBUG", f"Attempting fallback sendPhoto by URL: {photo_url}")
            data_url = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption_short, "parse_mode": "HTML"}
            r2 = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data=data_url, timeout=25)
            log("DEBUG", f"Telegram sendPhoto(by URL) response: {r2.status_code} - {short(r2.text)}")
            if r2.status_code in (200, 201):
                log("INFO", "Photo sent via Telegram by URL successfully (fallback).")
                if caption_short != full_text:
                    time.sleep(0.4)
                    send_message_text(full_text)
                return True
            else:
                log("WARN", f"sendPhoto (by URL) returned {r2.status_code} - {short(r2.text)}")
        except Exception as e:
            log("WARN", f"Exception during sendPhoto(by URL): {e}")

    # 3) Final fallback: send text only
    log("INFO", "All photo attempts failed or no photo available - sending text only.")
    send_message_text(full_text)
    return False

def send_message_text(text):
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=30,
        )
        if res.status_code not in (200, 201):
            log("WARN", f"sendMessage status {res.status_code}: {short(res.text)}")
        else:
            log("INFO", "sendMessage success (text message).")
        return res
    except Exception as e:
        log("ERROR", f"Exception sendMessage: {e}")
        return None

# =========================================
# MAIN per-lot processing (glue)
# =========================================
def process_and_send(lot):
    lot_id = lot.get("lotLelangId") or lot.get("id")
    if not lot_id:
        log("WARN", "Lot tanpa id, skip")
        return False

    detail = get_detail(lot_id)
    if not detail:
        log("WARN", f"Detail kosong untuk {lot_id}, akan kirim data minimal dari listing")
        detail_parsed = {
            "seller_name": lot.get("namaPenjual") or lot.get("namaOrganisasiPenjual"),
            "seller_phone": lot.get("nomorTelepon") or lot.get("nomor_telepon"),
            "seller_address": lot.get("alamat"),
            "seller_city": lot.get("namaLokasi"),
            "seller_prov": None,
            "cara_penawaran": lot.get("caraPenawaran") or lot.get("jenisPenawaran"),
            "uang_jaminan": lot.get("uangJaminan") or lot.get("uangJaminan"),
            "barangs": [],
            "organizer": {},
            "views": 0,
            "photos": lot.get("photos") or [],
        }
    else:
        detail_parsed = parse_detail(detail)

    full_text = build_message_text(lot, detail_parsed)
    photos = detail_parsed.get("photos") or []
    sent = send_to_telegram(full_text, photos)
    return sent

# =========================================
# MAIN (loop once)
# =========================================
def main():
    log("INFO", "Bot mulai jalan...")
    try:
        r = requests.get(API_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            log("ERROR", f"Gagal ambil listing, status {r.status_code} -- {short(r.text)}")
            return
        data = r.json().get("data", []) or []
        log("INFO", f"Ditemukan {len(data)} lot di API")
    except Exception as e:
        log("ERROR", f"Gagal ambil data dari API: {e}")
        return

    seen = load_seen()
    new_count = 0

    for lot in data:
        lot_id = lot.get("lotLelangId") or lot.get("id")
        if not lot_id:
            continue
        if lot_id in seen:
            continue

        try:
            process_and_send(lot)
        except Exception as e:
            log("ERROR", f"Gagal proses lot {lot_id}: {e}")
        seen.add(lot_id)
        new_count += 1

    save_seen(seen)
    if new_count == 0:
        log("INFO", "Tidak ada lot baru, semua sudah terkirim")
    else:
        log("INFO", f"{new_count} lot baru terkirim")
    log("INFO", "Bot selesai.")

if __name__ == "__main__":
    main()

# =========================================
# END OF SCRIPT
# =========================================
