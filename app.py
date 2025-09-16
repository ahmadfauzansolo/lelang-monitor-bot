import os
import json
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

# =========================================
# LOAD ENV
# =========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.lelang.go.id"

# =========================================
# LOGGING CONFIG
# =========================================
logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    level=logging.DEBUG
)

# =========================================
# TELEGRAM SEND FUNCTIONS
# =========================================
def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    if resp.status_code == 200:
        logging.info("sendMessage success (text message).")
    else:
        logging.warning(f"sendMessage failed: {resp.text}")

def send_telegram_photo(photo_url: str, caption: str):
    """Kirim foto dengan caption.
    Urutan: coba upload file dulu -> kalau gagal, coba by URL -> kalau gagal juga, kirim text only.
    """
    success = False

    # 1. Coba download dulu dan kirim sebagai file binary
    try:
        logging.debug(f"Attempting to download photo for upload: {photo_url}")
        r = requests.get(photo_url, timeout=10)
        logging.debug(f"Download status: {r.status_code} for {photo_url}")

        if r.status_code == 200:
            files = {"photo": ("image.jpg", r.content)}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
            upload_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            resp = requests.post(upload_url, data=data, files=files)

            if resp.status_code == 200:
                logging.info("sendPhoto success (binary upload).")
                success = True
            else:
                logging.warning(f"sendPhoto (binary upload) failed: {resp.text}")
    except Exception as e:
        logging.warning(f"Exception during photo upload: {e}")

    # 2. Kalau gagal, coba kirim by URL
    if not success:
        logging.debug(f"Attempting fallback sendPhoto by URL: {photo_url}")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "Markdown"})

        if resp.status_code == 200:
            logging.info("sendPhoto success (by URL).")
            success = True
        else:
            logging.warning(f"sendPhoto (by URL) returned {resp.status_code} - {resp.text}")

    # 3. Kalau tetap gagal, kirim text only
    if not success:
        logging.info("All photo attempts failed or no photo available - sending text only.")
        send_telegram_message(caption)

# =========================================
# FETCH DATA
# =========================================
def fetch_api():
    url = "https://api.lelang.go.id/api/v1/landing-page/filter"
    payload = {"limit": 10, "page": 1, "kategori": "", "instansi": "", "tipe": ""}
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("data", [])
    return []

def fetch_detail(lot_id):
    url = f"https://api.lelang.go.id/api/v1/landing-page/info/{lot_id}"
    for attempt in range(3):
        logging.debug(f"Fetch detail attempt {attempt+1} for {lot_id} -> {url}")
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            logging.debug(f"Detail fetch status 200 for {lot_id}")
            logging.info(f"Berhasil fetch detail {lot_id} (size: {len(resp.content)} bytes)")
            return resp.json().get("data", {})
    return {}

# =========================================
# MAIN
# =========================================
def main():
    logging.info("Bot mulai jalan...")

    lots = fetch_api()
    logging.info(f"Ditemukan {len(lots)} lot di API")

    # Load seen data
    seen_file = "seen_api.json"
    if os.path.exists(seen_file):
        with open(seen_file, "r") as f:
            seen_ids = json.load(f)
    else:
        logging.info("seen_api.json tidak ditemukan, membuat baru")
        seen_ids = []

    new_lots = [lot for lot in lots if lot["id"] not in seen_ids]

    if not new_lots:
        logging.info("Tidak ada lot baru ditemukan, tidak ada pengiriman")
    else:
        for lot in new_lots:
            detail = fetch_detail(lot["id"])
            if not detail:
                continue

            # Format pesan
            pesan = (
                f"{detail.get('judul', 'Tanpa Judul')}\n"
                f"📍 Lokasi: {detail.get('lokasi', '-')}\n"
                f"🏢 Instansi: {detail.get('instansi', '-')}\n"
                f"👤 Penjual: {detail.get('penjual', '-')}\n"
                f"🗓 {detail.get('tgl_mulai', '-')} → {detail.get('tgl_selesai', '-')}\n"
                f"💰 Nilai limit: Rp {detail.get('nilai_limit', '-')}\n"
                f"💵 Uang jaminan: Rp {detail.get('jaminan', '-')}\n"
                f"⚖️ Cara penawaran: {detail.get('cara_penawaran', '-')}\n"
                f"🔗 [Lihat detail lelang]({BASE_URL}{lot['url']})"
            )

            # Kirim dengan foto kalau ada
            photo_url = None
            if detail.get("foto"):
                photo_url = f"https://file.lelang.go.id{detail['foto'][0]}"

            if photo_url:
                send_telegram_photo(photo_url, pesan)
            else:
                send_telegram_message(pesan)

            seen_ids.append(lot["id"])

        with open(seen_file, "w") as f:
            json.dump(seen_ids, f)
        logging.info(f"Disimpan {len(new_lots)} lot ke {seen_file}")
        logging.info(f"{len(new_lots)} lot baru terkirim")

    logging.info("Bot selesai.")

# =========================================
# ENTRY POINT
# =========================================
if __name__ == "__main__":
    main()
