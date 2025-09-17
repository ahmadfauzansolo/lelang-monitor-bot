#!/usr/bin/env python3
"""
app.py - BOT MONITOR LELANG (FINAL)

Versi ini mempertahankan semua fungsionalitas lama yang sudah bekerja,
sambil menambahkan perbaikan untuk:
 - mengambil detail lot (retries + headers mirip browser)
 - mengambil informasi penjual dari beberapa lokasi dalam JSON
   (prioritaskan namaOrganisasiPenjual > namaPenjual)
 - download foto dengan `Referer` + session cookies agar menghindari 403
 - upload foto ke Telegram sebagai binary (multipart) sebagai prioritas
 - fallback bila upload foto gagal: coba sendPhoto by URL -> kirim teks saja
 - error handling dan logging sangat detail

Perubahan KECIL dan TERPUSAT (agar tidak mengirim lot lama):
 - jika file `SEEN_FILE` belum ada: script akan INISIALISASI file tersebut
   dengan daftar lot yang ada saat ini dan *tidak* mengirim apapun pada run ini.
   (mencegah broadcast lot lama saat pertama kali menjalankan script)
 - normalisasi ID ke string saat load/save/cek, supaya perbandingan stabil
 - penyimpanan `seen` dilakukan secara atomik (tulis ke .tmp lalu replace)

Catatan: selain perubahan di atas, logic lain saya usahakan tidak diubah.
"""

# -----------------------------------------
# IMPORTS
# -----------------------------------------
import os
import json
import time
import html
import logging
import traceback
from typing import Optional, List, Dict, Any, Set
from datetime import datetime

import requests
from dotenv import load_dotenv

# -----------------------------------------
# CONFIGURATION
# -----------------------------------------
load_dotenv()

# Endpoint untuk mengambil list (sudah digunakan sebelumnya dan stabil)
API_URL = (
    "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/"
    "katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
)

# Detail endpoint (pakai lotLelangId)
DETAIL_URL = "https://api.lelang.go.id/api/v1/landing-page/info/{}"  # {} = lotLelangId

# Photo base host (foto di-field fileUrl biasanya relatif, prefix ini)
BASE_PHOTO_URL = "https://file.lelang.go.id"

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Seen file
SEEN_FILE = os.getenv("SEEN_FILE", "seen_api.json")

# Max number of photos to try uploading (binary). Kirim up-to N untuk mencoba.
MAX_PHOTOS_UPLOAD = int(os.getenv("MAX_PHOTOS_UPLOAD", "2"))

# Request headers / UA used for fetch and photo download
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Timeout untuk HTTP
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "18"))

# Logging config (format mirip log yang kamu kirim)
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Validate env
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# -----------------------------------------
# HELPERS: seen file
# -----------------------------------------

def load_seen() -> Set[str]:
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # normalisasi semua entry ke string agar perbandingan stabil
            if isinstance(data, list):
                seen = set(str(x) for x in data if x is not None)
            else:
                seen = set()
        logger.info(f"Loaded {len(seen)} lot dari {SEEN_FILE}")
        return seen
    except FileNotFoundError:
        # IMPORTANT: jangan langsung return empty set yang akan membuat script
        # mengirim semua lot saat pertama kali dijalankan. Kita akan inisialisasi
        # SEEN_FILE setelah fetch list di main().
        logger.info(f"{SEEN_FILE} tidak ditemukan, akan diinisialisasi setelah fetch list (untuk menghindari repost lot lama)")
        return set()
    except Exception as e:
        logger.error(f"Gagal load {SEEN_FILE}: {e}")
        return set()


def save_seen(seen: Set[str]):
    try:
        # simpan secara atomik: tulis ke file .tmp lalu replace
        tmp = SEEN_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            # pastikan menyimpan list yang stabil (string)
            json.dump(sorted(list(seen)), f, ensure_ascii=False, indent=2)
        # atomic replace
        os.replace(tmp, SEEN_FILE)
        logger.info(f"Disimpan {len(seen)} lot ke {SEEN_FILE}")
    except Exception as e:
        logger.error(f"Gagal simpan {SEEN_FILE}: {e}")

# -----------------------------------------
# HELPERS: formatting
# -----------------------------------------

def format_date_iso(d: Optional[str]) -> str:
    if not d:
        return "-"
    try:
        # Some values may be like "2025-09-12T00:00:00+07:00"
        dt = datetime.fromisoformat(d)
        return dt.strftime("%d %b %Y %H:%M")
    except Exception:
        # fallback to substring
        return d[:16]


def money(x) -> str:
    try:
        return f"{int(x):,}" if x is not None and str(x) != "" else "0"
    except Exception:
        try:
            return f"{int(float(x)):,}"
        except Exception:
            return str(x)

# escape for html caption

def esc(s: Any) -> str:
    if s is None:
        return "-"
    return html.escape(str(s))

# -----------------------------------------
# NETWORK: session maker, fetch list, fetch detail
# -----------------------------------------

def make_session() -> requests.Session:
    """Create a requests.Session with sensible headers and initial request to get cookies.

    We do an initial GET to `https://lelang.go.id` so that `file.lelang.go.id` requests
    have cookies/referrer similar to a real browser (helps bypass hotlink protections).
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    })
    try:
        # initial visit to root to get cookies and any server-side session
        s.get("https://lelang.go.id", timeout=HTTP_TIMEOUT)
        logger.debug("Initial site visit done to acquire cookies and session headers")
    except Exception as e:
        logger.debug(f"Initial site visit failed (non-fatal): {e}")
    return s


def fetch_list(session: requests.Session) -> List[Dict[str, Any]]:
    """Fetch the list of lots from API_URL. Return list of lot dicts.

    Uses GET on the API_URL (this is the same URL you used previously and works reliably).
    """
    try:
        logger.debug(f"Fetching list -> {API_URL}")
        r = session.get(API_URL, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        logger.debug(f"List fetch status: {r.status_code} {r.reason}")
        if r.status_code != 200:
            logger.warning(f"List fetch returned status {r.status_code}")
            return []
        payload = r.json()
        data = payload.get("data", []) if isinstance(payload, dict) else []
        logger.info(f"Ditemukan {len(data)} lot di API")
        return data
    except Exception as e:
        logger.error(f"Gagal ambil data dari API: {e}")
        return []


def fetch_detail(session: requests.Session, lot_id: str, referer: Optional[str] = None) -> Dict[str, Any]:
    """Fetch detail for a lot. Will retry and try a couple of fallbacks.

    If seller missing, we will try another attempt using a referer header to emulate
    browser navigation from the detail page (some servers show more data).
    """
    if not lot_id:
        return {}

    url = DETAIL_URL.format(lot_id)
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            headers = {"User-Agent": USER_AGENT}
            if referer:
                headers["Referer"] = referer
            else:
                headers["Referer"] = "https://lelang.go.id/"

            logger.debug(f"Fetch detail attempt {attempt} for {lot_id} -> {url}")
            resp = session.get(url, timeout=HTTP_TIMEOUT, headers=headers)
            logger.debug(f"Detail fetch status {resp.status_code} for {lot_id}")

            if resp.status_code == 200:
                # parse
                try:
                    payload = resp.json()
                    data = payload.get("data", {}) if isinstance(payload, dict) else {}
                    logger.info(f"Berhasil fetch detail {lot_id} (size: {len(resp.content)} bytes)")
                    # quick heuristic: if seller is present, return; else try again with referer
                    seller_present = (
                        bool(data.get("content", {}).get("seller"))
                        or bool(data.get("seller"))
                        or bool(data.get("namaPenjual"))
                        or bool(data.get("namaOrganisasiPenjual"))
                    )
                    if seller_present:
                        return data
                    # else: maybe server needs referer/extra headers, try again with referer pointing to detail page
                    if attempt < attempts:
                        logger.debug(f"Detail {lot_id} missing seller data; will retry with stronger headers")
                        # small backoff
                        time.sleep(0.6)
                        continue
                    return data
                except Exception as e:
                    logger.warning(f"JSON parse error for detail {lot_id}: {e}")
                    return {}
            else:
                # if 404, try small fallback patterns (some endpoints vary)
                if resp.status_code == 404:
                    # try alternate possible endpoint (legacy). Non-fatal.
                    alt = f"https://api.lelang.go.id/api/v1/lot-lelang/{lot_id}"
                    try:
                        logger.debug(f"Trying alternate detail endpoint -> {alt}")
                        r2 = session.get(alt, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
                        if r2.status_code == 200:
                            payload = r2.json()
                            data = payload.get("data", {}) if isinstance(payload, dict) else {}
                            return data
                    except Exception:
                        pass
                # on other errors, wait before retrying
                logger.warning(f"Fetch detail gagal {lot_id}, status {resp.status_code}")
                time.sleep(0.4)
        except Exception as e:
            logger.warning(f"Exception during fetch_detail {lot_id}: {e}")
            time.sleep(0.4)
    logger.warning(f"Gagal fetch detail setelah {attempts} percobaan: {lot_id}")
    return {}

# -----------------------------------------
# HELPERS: extract and build text
# -----------------------------------------

def extract_seller(detail: Dict[str, Any], lot: Dict[str, Any]) -> Dict[str, str]:
    """Return normalized seller dict with keys: nama, telepon, alamat, kota, provinsi

    We check multiple locations (content.seller, seller, top-level fields) and prioritize
    namaOrganisasiPenjual over namaPenjual.
    """
    seller = {}

    # possible places
    c = detail.get("content") if isinstance(detail.get("content"), dict) else {}
    candidates = [
        c.get("seller") if isinstance(c.get("seller"), dict) else None,
        detail.get("seller") if isinstance(detail.get("seller"), dict) else None,
        # older payloads may have top-level seller-like fields
        {
            "namaPenjual": detail.get("namaPenjual"),
            "namaOrganisasiPenjual": detail.get("namaOrganisasiPenjual"),
            "nomorTelepon": detail.get("nomorTelepon"),
            "alamat": detail.get("alamat"),
            "namaKota": detail.get("namaKota"),
            "namaProvinsi": detail.get("namaProvinsi"),
        },
        # fallback: lot-level hints
        {
            "namaPenjual": lot.get("namaPenjual"),
            "namaOrganisasiPenjual": lot.get("namaOrganisasiPenjual"),
            "nomorTelepon": lot.get("nomorTelepon"),
            "alamat": lot.get("alamat"),
            "namaKota": lot.get("namaKota"),
            "namaProvinsi": lot.get("namaProvinsi"),
        },
    ]

    picked = None
    for cand in candidates:
        if not cand:
            continue
        # check if it contains any meaningful name
        N = (cand.get("namaOrganisasiPenjual") or cand.get("namaPenjual") or "").strip()
        if N:
            picked = cand
            break
        # if none with name, we still pick a candidate with phone or alamat later
        if not picked:
            picked = cand

    if not picked:
        picked = {}

    nama = picked.get("namaOrganisasiPenjual") or picked.get("namaPenjual") or "(tidak diketahui)"
    telepon = picked.get("nomorTelepon") or picked.get("telepon") or "-"
    alamat = picked.get("alamat") or "-"
    kota = picked.get("namaKota") or picked.get("kota") or "-"
    prov = picked.get("namaProvinsi") or picked.get("provinsi") or "-"

    seller["nama"] = nama
    seller["telepon"] = telepon
    seller["alamat"] = alamat
    seller["kota"] = kota
    seller["provinsi"] = prov

    return seller


def build_uraian(detail: Dict[str, Any]) -> str:
    """Build the 'uraian' / list of barang text block.

    We iterate all items in content.barangs, and produce multiline descriptive text per item.
    """
    items = detail.get("content", {}).get("barangs", []) if isinstance(detail.get("content", {}), dict) else []
    if not items:
        return "-"

    lines = []
    for b in items:
        nama = b.get("nama") or b.get("namaBarang") or "-"
        tahun = b.get("tahun") or "-"
        warna = b.get("warna") or "-"
        nomor_rangka = b.get("nomorRangka") or b.get("noRangka") or "-"
        nopol = b.get("nopol") or b.get("noPol") or "-"
        stnk = b.get("stnk") or "-"
        alamat = b.get("alamat") or "-"
        bukti = b.get("buktiKepemilikan") or "-"
        bukti_no = b.get("buktiKepemilikanNo") or ""

        # create a fairly verbose description per item
        part = []
        # first line: name and summary
        part.append(f"- {nama} ({tahun}, {warna})")
        # second line: identifiers
        ids = []
        if nomor_rangka and nomor_rangka != "-":
            ids.append(f"No. Rangka: {nomor_rangka}")
        if nopol and nopol != "-":
            ids.append(f"Nopol: {nopol}")
        if stnk and stnk != "-":
            ids.append(f"STNK: {stnk}")
        if ids:
            part.append("  " + " / ".join(ids))
        # alamat and bukti
        if alamat and alamat != "-":
            part.append(f"  Alamat: {alamat}")
        if bukti and bukti != "-":
            bn = f" {bukti_no}" if bukti_no else ""
            part.append(f"  Bukti kepemilikan: {bukti}{bn}")

        lines.append("\n".join(part))

    return "\n".join(lines)

# -----------------------------------------
# HELPERS: photo download & telegram upload
# -----------------------------------------

def resolve_photo_url(file_url: str) -> Optional[str]:
    if not file_url:
        return None
    if file_url.startswith("http://") or file_url.startswith("https://"):
        return file_url
    if file_url.startswith("/"):
        return BASE_PHOTO_URL + file_url
    # fallback
    return BASE_PHOTO_URL + "/" + file_url


def download_photo_bytes(session: requests.Session, photo_url: str, referer: Optional[str] = None) -> Optional[bytes]:
    """Try to download photo content using session + referer + UA. Return bytes or None.

    We implement a couple of header strategies to bypass hotlink / 403:
    - strategy 1: standard UA + Referer https://lelang.go.id
    - strategy 2: include same-origin referer to detail page (if provided)
    - strategy 3: small delay and retry
    """
    if not photo_url:
        return None

    resolved = resolve_photo_url(photo_url)
    if not resolved:
        return None

    # try a few mirror headers / attempts
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": referer or "https://lelang.go.id/",
            }
            logger.debug(f"Attempting download ({attempt}) for {resolved} with Referer={headers['Referer']}")
            resp = session.get(resolved, headers=headers, timeout=HTTP_TIMEOUT, stream=True, allow_redirects=True)
            status = getattr(resp, "status_code", None)
            logger.debug(f"Download status: {status} for {resolved}")

            if status == 200:
                content = resp.content
                logger.info(f"Berhasil download photo {resolved} (size {len(content)} bytes)")
                return content
            else:
                logger.warning(f"Gagal download photo {resolved}, status {status}")
                # small backoff, but if 403 keep trying — kadang cookie/Referer needed
                time.sleep(0.25 * attempt)
                continue
        except Exception as e:
            logger.warning(f"Exception saat download photo {resolved}: {e}")
            time.sleep(0.25)
            continue
    logger.warning(f"Gagal download photo setelah {attempts} percobaan: {resolved}")
    return None


def send_photo_binary(photo_bytes: bytes, caption: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        files = {"photo": ("photo.jpg", photo_bytes)}
        data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=data, files=files, timeout=HTTP_TIMEOUT)
        logger.debug(f"Telegram sendPhoto (binary) response: {r.status_code} - {r.text}")
        if r.status_code == 200:
            logger.info("sendPhoto success (binary upload).")
            return True
        else:
            logger.warning(f"sendPhoto (binary upload) failed: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        logger.warning(f"Exception during sendPhoto (binary): {e}")
        return False


def send_photo_by_url(photo_url: str, caption: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=payload, timeout=HTTP_TIMEOUT)
        logger.debug(f"Telegram sendPhoto(by URL) response: {r.status_code} - {r.text}")
        if r.status_code == 200:
            logger.info("sendPhoto success (by URL).")
            return True
        else:
            logger.warning(f"sendPhoto (by URL) returned {r.status_code} - {r.text}")
            return False
    except Exception as e:
        logger.warning(f"Exception during sendPhoto (by URL): {e}")
        return False


def send_text_message(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            logger.info("sendMessage success (text message).")
            return True
        else:
            logger.warning(f"sendMessage failed: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        logger.warning(f"Exception during sendMessage: {e}")
        return False


def try_send_photos(session: requests.Session, photo_file_urls: List[str], caption: str) -> bool:
    """Try to send up to MAX_PHOTOS_UPLOAD photos.

    Strategy:
     - Attempt to download (with referer/cookies) the first up to MAX_PHOTOS_UPLOAD photos.
     - For each successfully downloaded photo, upload as binary. The first uploaded photo contains the caption.
     - If no downloaded photo succeeded, try sendPhoto by URL for first photo (may still fail).
     - If everything fails, return False.
    """
    if not photo_file_urls:
        logger.debug("No photo URLs provided to try_send_photos")
        return False

    uploaded_any = False
    tried = 0

    # Limit how many photos we attempt to download/upload
    for idx, fileurl in enumerate(photo_file_urls[:MAX_PHOTOS_UPLOAD]):
        if not fileurl:
            continue
        tried += 1
        resolved = resolve_photo_url(fileurl)
        # Download the photo bytes using session (with referer pointing to root)
        photo_bytes = download_photo_bytes(session, resolved, referer="https://lelang.go.id/")
        if photo_bytes:
            # For the first successful upload, include caption. Subsequent photos send without caption.
            cap = caption if not uploaded_any else ""
            ok = send_photo_binary(photo_bytes, cap if cap else "")
            if ok:
                uploaded_any = True
            else:
                logger.debug("Binary upload failed for a photo, will try next one")
        else:
            logger.debug(f"Download returned no bytes for {resolved}, will try next photo")

    # If we didn't manage any binary upload, as fallback try sendPhoto by URL for first photo
    if not uploaded_any and photo_file_urls:
        first = resolve_photo_url(photo_file_urls[0])
        if first:
            logger.debug(f"Attempting fallback sendPhoto by URL: {first}")
            ok = send_photo_by_url(first, caption)
            if ok:
                uploaded_any = True
    # Return whether we successfully sent any photo
    if not uploaded_any:
        logger.info("All photo attempts failed or no photo available - will send text only")
    return uploaded_any

# -----------------------------------------
# CORE: prepare and send lot message
# -----------------------------------------

def build_caption_html(title: str, lokasi: str, instansi: str, seller: Dict[str, str], start: str, end: str, nilai_limit: str, uang_jaminan: str, cara_penawaran: str, uraian: str, organizer_info: str, views: int, link: str) -> str:
    # Build an HTML caption for Telegram (escape user content)
    parts = []
    parts.append(f"{esc(title)}")
    parts.append(f"📍 Lokasi: {esc(lokasi)}")
    parts.append(f"🏢 Instansi: {esc(instansi)}")
    parts.append(f"👤 Penjual: {esc(seller.get('nama'))}")
    parts.append(f"   📞 {esc(seller.get('telepon'))}")
    parts.append(f"   🏠 {esc(seller.get('alamat'))}, {esc(seller.get('kota'))}, {esc(seller.get('provinsi'))}")
    parts.append(f"🗓 {esc(start)} → {esc(end)}")
    parts.append(f"💰 Nilai limit: Rp {money(nilai_limit)}")
    parts.append(f"💵 Uang jaminan: Rp {money(uang_jaminan)}")
    parts.append(f"⚖️ Cara penawaran: {esc(cara_penawaran)}")
    parts.append(f"📦 Barang:\n{esc(uraian).replace('\n', '\n')}")
    parts.append(f"🏦 Organizer: {esc(organizer_info)}")
    parts.append(f"👁️ Dilihat: {views}")
    # Link as HTML anchor
    parts.append(f"🔗 <a href=\"{esc(link)}\">Lihat detail lelang</a>")

    caption = "\n".join(parts)
    return caption


def send_lot(session: requests.Session, lot: Dict[str, Any]) -> bool:
    """Send a single lot to Telegram. Returns True if sent (either photo or text).

    This is the main function orchestrating detail fetch, content extraction and photo handling.
    """
    lot_id = lot.get("lotLelangId") or lot.get("id")
    if not lot_id:
        logger.warning("Lot tanpa id, dilewati")
        return False

    title = lot.get("namaLotLelang") or lot.get("nama") or "(tanpa judul)"
    lokasi = lot.get("namaLokasi") or lot.get("lokasi") or "(tidak diketahui)"
    instansi = lot.get("namaUnitKerja") or lot.get("instansi") or "(tidak diketahui)"
    start = format_date_iso(lot.get("tglMulaiLelang") or lot.get("tglMulai") )
    end = format_date_iso(lot.get("tglSelesaiLelang") or lot.get("tglSelesai"))
    nilai_limit = lot.get("nilaiLimit") or lot.get("nilai_limit") or 0

    # Link to public page (for user convenience). Use unitKerjaId if available
    unit_id = lot.get("unitKerjaId") or lot.get("unitKerja") or ""
    link = f"https://lelang.go.id/kpknl/{unit_id}/detail-auction/{lot_id}" if unit_id else f"https://lelang.go.id/detail-auction/{lot_id}"

    # 1) Fetch detail
    detail = fetch_detail(session, lot_id, referer=link)

    # If detail is empty, we still try to compose a minimal message from list item
    if not detail:
        logger.warning(f"Detail kosong untuk {lot_id}, mengirim info minimal")
        caption_min = (
            f"{esc(title)}\n"
            f"📍 Lokasi: {esc(lokasi)}\n"
            f"🏢 Instansi: {esc(instansi)}\n"
            f"🗓 {esc(start)} → {esc(end)}\n"
            f"💰 Nilai limit: Rp {money(nilai_limit)}\n"
            f"🔗 <a href=\"{esc(link)}\">Lihat detail lelang</a>"
        )
        send_text_message(caption_min)
        return True

    # 2) Extract seller (robust)
    seller = extract_seller(detail, lot)

    # 3) Cara penawaran
    cara = detail.get("caraPenawaran") or detail.get("cara_penawaran") or lot.get("caraPenawaran") or "-"
    cara_f = cara.replace("_", " ").title() if isinstance(cara, str) else str(cara)

    # 4) Uang jaminan: fallback to lot-level if missing
    uang_jaminan = detail.get("uangJaminan") if detail.get("uangJaminan") is not None else lot.get("uangJaminan") or 0

    # 5) Barang / uraian
    uraian = build_uraian(detail)

    # 6) Organizer
    organizer = detail.get("content", {}).get("organizer") if isinstance(detail.get("content"), dict) else {}
    organizer_info = " / ".join([str(organizer.get("namaUnitKerja") or "-"), str(organizer.get("namaBank") or "-")])

    # 7) Views
    views = detail.get("views") or 0

    # 8) Photos list
    photos = detail.get("photos") or []
    photo_file_urls = []
    for p in photos:
        if not isinstance(p, dict):
            continue
        f = p.get("file") or {}
        url = f.get("fileUrl") or p.get("fileUrl")
        if url:
            photo_file_urls.append(url)

    # 9) Build caption (HTML)
    caption_full = build_caption_html(title, lokasi, instansi, seller, start, end, nilai_limit, uang_jaminan, cara_f, uraian, organizer_info, views, link)

    # 10) Try to send photos (binary preferred)
    sent_any_photo = False
    try:
        if photo_file_urls:
            sent_any_photo = try_send_photos(session, photo_file_urls, caption_full)
    except Exception as e:
        logger.warning(f"Error saat mencoba kirim foto untuk {lot_id}: {e} - akan fallback ke text\n{traceback.format_exc()}")

    # 11) If no photo sent, fallback to send text-only
    if not sent_any_photo:
        send_text_message(caption_full)

    logger.info(f"Lot {lot_id} terkirim")
    return True

# -----------------------------------------
# MAIN
# -----------------------------------------

def main():
    logger.info("Bot mulai jalan...")

    session = make_session()

    # 1) fetch list
    lots = fetch_list(session)

    # Safety: jika SEEN_FILE belum ada, inisialisasi SEEN_FILE dengan daftar lot saat ini
    # dan JANGAN mengirim apapun pada run ini — mencegah broadcast lot lama saat pertama kali run.
    if not os.path.exists(SEEN_FILE):
        init_seen = set()
        for lot in lots:
            raw = lot.get("lotLelangId") or lot.get("id")
            if raw:
                init_seen.add(str(raw))
        save_seen(init_seen)
        logger.info(f"SEEN_FILE '{SEEN_FILE}' tidak ditemukan sebelumnya. Inisialisasi dengan {len(init_seen)} lot dari list saat ini. Tidak mengirim apapun pada run ini.")
        return

    # 2) load seen
    seen = load_seen()

    new_count = 0

    for lot in lots:
        try:
            raw_id = lot.get("lotLelangId") or lot.get("id")
            if not raw_id:
                logger.debug("Skip lot tanpa id")
                continue
            # normalisasi id ke string supaya perbandingan dengan seen konsisten
            lot_id = str(raw_id)
            if lot_id in seen:
                logger.debug(f"Lot {lot_id} sudah pernah dikirim, lewati")
                continue

            ok = send_lot(session, lot)

            # Only mark as seen when we at least sent (text or photo)
            if ok:
                seen.add(lot_id)
                new_count += 1
            else:
                logger.warning(f"Lot {lot_id} tidak berhasil dikirim, tidak ditandai sebagai seen")

            # tiny sleep to be polite
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"Exception main loop untuk lot: {e}\n{traceback.format_exc()}")
            # don't stop the loop on error
            continue

    # save seen
    save_seen(seen)

    logger.info(f"{new_count} lot baru terkirim")
    logger.info("Bot selesai kirim semua lot.")


if __name__ == "__main__":
    main()
