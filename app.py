import os
import json
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# =========================================
# CONFIG
# =========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.lelang.go.id/kpknl"   # sesuaikan kalau beda
KPKNL_ID = os.getenv("KPKNL_ID")
AUCTION_ID = os.getenv("AUCTION_ID")
SEEN_FILE = "seen_api.json"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
)

# =========================================
# FETCH LOTS
# =========================================
def fetch_lots():
    url = f"{BASE_URL}/{KPKNL_ID}/detail-auction/{AUCTION_ID}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()

        lots = data.get("lots", [])
        logging.info(f"Ditemukan {len(lots)} lot di API")

        if lots:
            logging.info("Contoh lot mentah dari API:\n" + json.dumps(lots[0], indent=2, ensure_ascii=False))

        return lots
    except Exception as e:
        logging.error(f"Gagal fetch lots: {e}")
        return []

# =========================================
# LOAD & SAVE SEEN LOTS
# =========================================
def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f)

# =========================================
# TELEGRAM SEND
# =========================================
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            logging.info("Pesan terkirim ke Telegram, status 200")
        else:
            logging.warning(f"Gagal kirim Telegram, status {r.status_code}, resp: {r.text}")
    except Exception as e:
        logging.error(f"Error kirim Telegram: {e}")

# =========================================
# FORMAT LOT
# =========================================
def format_lot(lot):
    """ Ambil field dari JSON, kalau tidak ada -> '-' """
    uang_jaminan = lot.get("uang_jaminan", "-")
    cara_penawaran = lot.get("cara_penawaran", "-")
    kode_lot = lot.get("kode_lot", "-")
    batas_setor_jaminan = lot.get("batas_setor_jaminan", "-")

    if uang_jaminan == "-" or cara_penawaran == "-":
        logging.warning(f"Lot {lot.get('id','?')} tidak punya field lengkap: {lot.keys()}")

    return (
        f"🏷️ Lot ID: {lot.get('id','-')}\n"
        f"Uang jaminan: {uang_jaminan}\n"
        f"⚙️ Cara penawaran: {cara_penawaran}\n"
        f"🔑 Kode Lot: {kode_lot}\n"
        f"⏳ Batas setor jaminan: {batas_setor_jaminan}"
    )

# =========================================
# MAIN
# =========================================
def main():
    logging.info("=== Bot dimulai ===")

    lots = fetch_lots()
    seen = load_seen()
    new_lots = []

    for lot in lots:
        lot_id = lot.get("id")
        if lot_id and lot_id not in seen:
            new_lots.append(lot)

    if not new_lots:
        logging.info("Tidak ada lot baru ditemukan, tidak dikirim")
        return

    logging.info(f"{len(new_lots)} lot baru ditemukan")

    for lot in new_lots:
        msg = format_lot(lot)
        send_to_telegram(msg)
        seen.append(lot.get("id"))

    save_seen(seen)
    logging.info(f"Selesai kirim {len(new_lots)} lot baru")


if __name__ == "__main__":
    main()
