# =========================================
# APP.PY - BOT MONITOR LELANG (FINAL, TELITI)
# =========================================
# Fitur utama:
# - Ambil list lot dari API katalog.
# - Untuk setiap lot baru, fetch detail lewat endpoint
#   https://api.lelang.go.id/api/v1/landing-page/info/{lotLelangId}
# - Robust parsing: menangani variasi struktur ('content.barangs'
#   atau 'content.lot.barang', fields 'nama' vs 'namaBarang', dsb.)
# - Retry fetch detail (3x) dengan backoff kecil.
# - Semua barang dicetak (tidak dipotong).
# - Escaping HTML sebelum dikirim ke Telegram (parse_mode=HTML).
# - Jika caption terlalu panjang, kirim foto + kirim teks lengkap terpisah.
# - Simpan seen ids di seen_api.json.
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
# HELPERS - file seen
# =========================================
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            seen_list = json.load(f)
            seen = set(seen_list)
        print(f"[INFO] Loaded {len(seen)} lot dari {SEEN_FILE}")
        return seen
    except FileNotFoundError:
        print(f"[INFO] {SEEN_FILE} tidak ditemukan, membuat baru")
        return set()
    except Exception as e:
        print(f"[ERROR] Gagal load {SEEN_FILE}: {e}")
        return set()


def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
        print(f"[INFO] Disimpan {len(seen)} lot ke {SEEN_FILE}")
    except Exception as e:
        print(f"[ERROR] Gagal simpan {SEEN_FILE}: {e}")


# =========================================
# UTILITIES: formatting & safe-get
# =========================================
def format_date_iso(d, with_time=False):
    """Format ISO -> 'DD Mon YYYY HH:MM' atau 'DD Mon YYYY'."""
    try:
        if not d:
            return "-"
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y %H:%M") if with_time else dt.strftime("%d %b %Y")
    except Exception:
        return d[:16] if d else "-"


def format_rupiah(v):
    """Format numeric/string to 'Rp 12,345,000' or return '-'."""
    try:
        if v is None or v == "":
            return "Rp -"
        n = int(float(str(v)))
        return f"Rp {n:,}"
    except Exception:
        return "Rp -"


def html_escape(s):
    """Escape &, <, > for Telegram HTML mode (minimal)."""
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def first_non_empty(*args):
    """Return the first arg that's not None/empty-string."""
    for a in args:
        if a is None:
            continue
        if isinstance(a, str) and a.strip() == "":
            continue
        return a
    return None


# =========================================
# FETCH DETAIL with retries
# =========================================
def get_detail(lot_id, retries=3, backoff=0.5):
    """Fetch detail endpoint (landing-page/info/{lot_id}) with retries."""
    if not lot_id:
        return {}
    url = DETAIL_URL.format(lot_id)
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                return r.json().get("data", {}) or {}
            else:
                print(f"[WARN] Fetch detail gagal {lot_id}, status {r.status_code} (attempt {attempt})")
        except Exception as e:
            last_exc = e
            print(f"[WARN] Exception fetch detail {lot_id} attempt {attempt}: {e}")
        time.sleep(backoff * attempt)
    if last_exc:
        print(f"[ERROR] Semua percobaan fetch detail gagal untuk {lot_id}: {last_exc}")
    return {}


# =========================================
# PARSE DETAIL: robustly pick fields from possible locations
# =========================================
def parse_detail(detail):
    """
    Given 'detail' = r.json().get('data', {}), return a dict with:
    - seller_name, seller_phone, seller_address, seller_city, seller_prov
    - cara_penawaran
    - uang_jaminan
    - barangs_list (list of dict per item)
    - organizer_info, views, photos_list
    """
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

    # often the 'content' container
    content = detail.get("content", {}) or {}

    # --- seller (several key-name variations observed) ---
    seller = content.get("seller") or detail.get("seller") or {}
    # common keys seen in examples: 'namaOrganisasiPenjual', 'namaPenjual'
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
        seller.get("nomorTelepon"),
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

    # --- cara penawaran: try multiple paths ---
    out["cara_penawaran"] = first_non_empty(
        detail.get("caraPenawaran"),
        content.get("caraPenawaran"),
        (content.get("lot") or {}).get("caraPenawaran"),
        detail.get("cara_penawaran"),
    ) or None

    # --- uang jaminan ---
    out["uang_jaminan"] = first_non_empty(
        detail.get("uangJaminan"),
        detail.get("uang_jaminan"),
        content.get("uangJaminan"),
    )

    # --- barangs: multiple possible locations/names ---
    barangs = content.get("barangs")
    if not barangs:
        lot_block = content.get("lot") or {}
        barangs = lot_block.get("barang") or lot_block.get("barangs")
    if not barangs:
        # fallback to some alternate keys
        barangs = detail.get("barangs") or []

    # normalize each barang item into dict with common keys
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

    # --- organizer (common fields) ---
    organizer = content.get("organizer") or detail.get("organizer") or {}
    out["organizer"] = {
        "namaUnitKerja": organizer.get("namaUnitKerja") or organizer.get("nama_unit_kerja") or organizer.get("namaUnit"),
        "namaBank": organizer.get("namaBank") or organizer.get("bank"),
        "nomorTelepon": organizer.get("nomorTelepon") or organizer.get("nomor_telepon") or organizer.get("telepon"),
        "alamat": organizer.get("alamat"),
    }

    # --- views, photos ---
    out["views"] = first_non_empty(detail.get("views"), detail.get("jumlahView"), 0) or 0
    out["photos"] = detail.get("photos") or content.get("photos") or detail.get("photos", []) or []

    return out


# =========================================
# BUILD CAPTION / TEXT (all barang included)
# =========================================
def build_message_text(lot, detail_parsed):
    # basic lot fields (some come from listing 'lot', some from detail)
    title = lot.get("namaLotLelang") or lot.get("namaLot") or "(tanpa judul)"
    lokasi = lot.get("namaLokasi") or lot.get("lokasi") or "-"
    instansi = lot.get("namaUnitKerja") or lot.get("namaUnit") or "-"
    start = format_date_iso(lot.get("tglMulaiLelang") or lot.get("tglMulai"), with_time=True)
    end = format_date_iso(lot.get("tglSelesaiLelang") or lot.get("tglSelesai"), with_time=True)

    # seller
    seller_name = detail_parsed.get("seller_name") or "(tidak diketahui)"
    seller_phone = detail_parsed.get("seller_phone") or "-"
    seller_addr = detail_parsed.get("seller_address") or "-"
    seller_city = detail_parsed.get("seller_city") or "-"
    seller_prov = detail_parsed.get("seller_prov") or "-"

    # money
    nilai_limit = format_rupiah(first_non_empty(lot.get("nilaiLimit"), lot.get("nilai_limit"), None))
    uang_jaminan = format_rupiah(first_non_empty(detail_parsed.get("uang_jaminan"), detail_parsed.get("uang_jaminan"), lot.get("uangJaminan"), lot.get("uangJaminan")))  # try multiple

    # cara penawaran
    cara = detail_parsed.get("cara_penawaran") or "-"
    if isinstance(cara, str):
        cara = cara.replace("_", " ").title()

    # barang: build full multi-line text for all items (no truncation)
    barang_lines = []
    for i, b in enumerate(detail_parsed.get("barangs", []) or [], start=1):
        # Format consistent and readable
        nm = b.get("nama", "-")
        tahun = b.get("tahun", "-")
        warna = b.get("warna", "-")
        rangka = b.get("nomor_rangka", "-")
        nopol = b.get("nopol", "-")
        alamat_b = b.get("alamat", "-")
        bukti = b.get("bukti", "-")
        bukti_no = b.get("bukti_no", "-")
        stnk = b.get("stnk", "-")

        # Compose block for each barang
        block = []
        # main line: name + summary
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
        # alamat
        if alamat_b and alamat_b != "-":
            block.append(f"  Alamat: {alamat_b}")
        # bukti kepemilikan
        bk = bukti
        if bk and bk != "-":
            if bukti_no and bukti_no != "-":
                block.append(f"  Bukti kepemilikan: {bk} {bukti_no}")
            else:
                block.append(f"  Bukti kepemilikan: {bk}")
        barang_lines.append("\n".join(block))

    barang_text = "\n".join(barang_lines) if barang_lines else "-"

    # organizer
    organizer = detail_parsed.get("organizer", {}) or {}
    organizer_info = f"{organizer.get('namaUnitKerja') or '-'} / {organizer.get('namaBank') or '-'}"

    views = detail_parsed.get("views") or 0

    # link
    link = f"https://lelang.go.id/kpknl/{lot.get('unitKerjaId')}/detail-auction/{lot.get('lotLelangId') or lot.get('id')}"

    # Compose full text (HTML-escaped)
    # We escape each dynamic part to avoid breaking HTML parse_mode
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
    # barang lines need to be escaped too, but keep newlines
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
# SEND to TELEGRAM (photo + text handling)
# =========================================
def send_to_telegram(full_text, photos):
    """
    photos: list of photo dicts as returned by API (each may have 'file'->'fileUrl')
    Strategy:
    - If there is a photo, try to send photo plus a short caption (first 800 chars).
      Then send full_text as separate message (so we don't exceed caption limit).
    - If no photo, send full_text with sendMessage.
    """
    # Telegram caption limit ~1024 chars. We'll use safe_cap = 800.
    safe_caption_len = 800

    # find photo_url (prefer iscover)
    photo_url = None
    if photos:
        for p in photos:
            if p.get("iscover"):
                f = p.get("file", {}) or {}
                if f.get("fileUrl"):
                    photo_url = f.get("fileUrl")
                    break
        if not photo_url:
            # fallback to first photo
            f = photos[0].get("file", {}) if photos[0].get("file") else {}
            if f.get("fileUrl"):
                photo_url = f.get("fileUrl")
    if photo_url:
        if not photo_url.startswith("http"):
            photo_url = BASE_PHOTO_URL + photo_url
        # prepare short caption (first lines of full_text) — safe HTML
        caption_short = full_text
        if len(caption_short) > safe_caption_len:
            caption_short = caption_short[:safe_caption_len].rsplit("\n", 1)[0] + "\n\u2026"  # add ellipsis
        # send photo
        try:
            img_resp = requests.get(photo_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if img_resp.status_code == 200:
                files = {"photo": ("img.jpg", img_resp.content)}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption_short, "parse_mode": "HTML"}
                r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data=data, files=files, timeout=30)
                if r.status_code in (200, 201):
                    # send full text as separate message if truncated or if caption_short != full_text
                    if caption_short != full_text:
                        time.sleep(0.5)
                        send_message_text(full_text)
                    return True
                else:
                    print(f"[WARN] sendPhoto status {r.status_code}, fallback to sendMessage")
            else:
                print(f"[WARN] Gagal download photo {photo_url}, status {img_resp.status_code}")
        except Exception as e:
            print(f"[WARN] Exception saat kirim photo: {e}")

    # fallback: kirim text saja
    send_message_text(full_text)
    return False


def send_message_text(text):
    """Send long text via sendMessage (HTML)."""
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=30,
        )
        if res.status_code not in (200, 201):
            print(f"[WARN] sendMessage status {res.status_code}: {res.text}")
        return res
    except Exception as e:
        print(f"[ERROR] Exception sendMessage: {e}")
        return None


# =========================================
# MAIN send_message per lot (glue)
# =========================================
def process_and_send(lot):
    """
    For a given lot (from listing), fetch detail, parse, build text, send to Telegram.
    Returns True if photo-sent (or any send), False otherwise.
    """
    lot_id = lot.get("lotLelangId") or lot.get("id")
    if not lot_id:
        print("[WARN] Lot tanpa id, skip")
        return False

    # fetch detail (robust)
    detail = get_detail(lot_id)
    if not detail:
        # still try to build from listing minimal info
        print(f"[WARN] Detail kosong untuk {lot_id}, akan kirim data minimal dari listing")
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

    # build full text
    full_text = build_message_text(lot, detail_parsed)

    # send
    photos = detail_parsed.get("photos") or []
    sent = send_to_telegram(full_text, photos)
    return sent


# =========================================
# MAIN (loop once)
# =========================================
def main():
    print(f"[{datetime.now()}] Bot mulai jalan...")

    try:
        r = requests.get(API_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            print(f"[ERROR] Gagal ambil listing, status {r.status_code}")
            return
        data = r.json().get("data", []) or []
        print(f"[INFO] Ditemukan {len(data)} lot di API")
    except Exception as e:
        print(f"[ERROR] Gagal ambil data dari API: {e}")
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
            print(f"[ERROR] Gagal proses lot {lot_id}: {e}")
        seen.add(lot_id)
        new_count += 1

    save_seen(seen)
    if new_count == 0:
        print(f"[{datetime.now()}] [INFO] Tidak ada lot baru, semua sudah terkirim")
    else:
        print(f"[{datetime.now()}] [INFO] {new_count} lot baru terkirim")
    print(f"[{datetime.now()}] Bot selesai.")

if __name__ == "__main__":
    main()
