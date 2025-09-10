#!/usr/bin/env python3
import os
import time
import json
import requests
import logging
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Config via env vars
API_URL = os.getenv("API_URL",
    "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
)
KEYWORD_INSTANSI = os.getenv("KEYWORD_INSTANSI", "KPKNL Surakarta")  # bisa koma-separate
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "600"))  # default 600s = 10 menit
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEEN_FILE = os.getenv("SEEN_FILE", "seen_api.json")
USER_AGENT = "lelang-monitor/1.0"

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID harus diset di environment variables.")
    raise SystemExit(1)

KEYWORDS: List[str] = [k.strip().lower() for k in KEYWORD_INSTANSI.split(",") if k.strip()]

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except Exception:
        return set()

def save_seen(seen_set):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen_set), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("Gagal menyimpan seen file: %s", e)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
    try:
        r = requests.post(url, data=payload, timeout=20)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error("Gagal kirim message: %s", e)
        return False

def send_telegram_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    # Telegram menerima URL langsung via field 'photo'
    payload = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=30)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.warning("Gagal kirim photo (fallback ke message). Error: %s", e)
        # fallback: kirim caption sebagai message
        return send_telegram_message(caption)

def format_msg(lot):
    lot_id = lot.get("id", "")
    title = lot.get("namaLotLelang", "(tanpa judul)")
    instansi = lot.get("namaUnitKerja", "")
    start = lot.get("tglMulaiLelang", "")
    end = lot.get("tglSelesaiLelang", "")
    limit = lot.get("nilaiLimit", "")
    jaminan = lot.get("uangJaminan", "")
    detail_url = f"https://lelang.go.id/lot-lelang/{lot_id}"

    msg = f"🔔 <b>Lelang baru dari {instansi}</b>\n\n"
    msg += f"<b>{title}</b>\n"
    msg += f"🗓 {start} → {end}\n"
    if limit:
        msg += f"💰 Nilai Limit: Rp {limit}\n"
    if jaminan:
        msg += f"💵 Uang Jaminan: Rp {jaminan}\n"
    msg += f"🔗 <a href='{detail_url}'>Detail Lelang</a>"
    return msg

def find_cover_url(lot):
    for p in lot.get("photos", []) or []:
        if p.get("iscover"):
            fu = p.get("file", {}).get("fileUrl")
            if fu:
                return "https://lelang.go.id" + fu
    # fallback: first photo
    first = (lot.get("photos") or [])[:1]
    if first:
        fu = first[0].get("file", {}).get("fileUrl")
        if fu:
            return "https://lelang.go.id" + fu
    return None

def matches_instansi(instansi_text: str) -> bool:
    if not KEYWORDS:
        return True
    itm = (instansi_text or "").lower()
    return any(k in itm for k in KEYWORDS)

def check_once(seen):
    logging.info("Memanggil API: %s", API_URL)
    try:
        r = requests.get(API_URL, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logging.error("Gagal ambil data API: %s", e)
        return seen

    items = data.get("data", []) or []
    logging.info("Ditemukan %d lot", len(items))

    new_found = False
    for lot in items:
        lot_id = lot.get("id")
        if not lot_id:
            continue
        if lot_id in seen:
            continue
        instansi = lot.get("namaUnitKerja", "")
        if not matches_instansi(instansi):
            continue

        msg = format_msg(lot)
        cover = find_cover_url(lot)
        # kirim photo kalau ada, else message
        ok = False
        if cover:
            ok = send_telegram_photo(cover, msg)
        else:
            ok = send_telegram_message(msg)
        if ok:
            logging.info("Notifikasi dikirim untuk lot: %s", lot_id)
            seen.add(lot_id)
            new_found = True
        else:
            logging.warning("Gagal mengirim notifikasi untuk lot: %s — tetap menandai sebagai seen agar tidak loop", lot_id)
            seen.add(lot_id)

    if new_found:
        save_seen(seen)
    return seen

def main():
    seen = load_seen()
    logging.info("Monitor siap. Interval: %s detik. Keywords: %s", CHECK_INTERVAL, KEYWORDS)
    while True:
        try:
            seen = check_once(seen)
        except Exception as e:
            logging.exception("Error saat pengecekan: %s", e)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
