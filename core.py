#!/usr/bin/env python3
"""
core.py - Fungsi inti bot lelang
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

# ==============================
# TELEGRAM CONFIG
# ==============================
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TG_API = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage" if TG_TOKEN else None

# ==============================
# SESSION & FETCH
# ==============================
BASE_URL = "https://api.lelang.go.id/api/v1"
KPKNL_ID = "6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a"  # bisa disesuaikan
CATEGORIES = ["Mobil", "Motor"]

def make_session():
    """Bikin session HTTP dengan header default"""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; AuctionBot/1.0)"
    })
    return s

def fetch_list(session):
    """Ambil daftar lot"""
    url = f"{BASE_URL}/landing-page-kpknl/{KPKNL_ID}/katalog-lot-lelang"
    params = [("namakategori[]", cat) for cat in CATEGORIES]
    try:
        r = session.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        lots = data.get("data", [])
        logger.info(f"API balas {len(lots)} lot")
        return lots
    except Exception as e:
        logger.error(f"Gagal fetch list: {e}")
        return []

def fetch_detail(session, lot_id):
    """Ambil detail lot"""
    url = f"{BASE_URL}/lot-lelang/{lot_id}"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("data", {})
    except Exception as e:
        logger.error(f"Gagal fetch detail {lot_id}: {e}")
        return {}

# ==============================
# TELEGRAM SEND
# ==============================
def send_to_telegram(text):
    if not TG_API or not TG_CHAT_ID:
        logger.warning("Telegram config tidak lengkap")
        return False
    try:
        r = requests.post(TG_API, json={
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
        if r.status_code == 200:
            return True
        else:
            logger.error(f"Telegram error {r.status_code}: {r.text}")
            return False
    except Exception as e:
        logger.error(f"Gagal kirim Telegram: {e}")
        return False

def format_lot(detail):
    """Format pesan lot"""
    title = detail.get("judulLot", "Tanpa Judul")
    harga = detail.get("hargaLimit", "-")
    lokasi = detail.get("alamatBarang", "-")
    tgl = detail.get("tanggalLelang", "-")
    url = f"https://lelang.go.id/lot-lelang/{detail.get('id', '')}"

    return (
        f"📢 <b>{title}</b>\n\n"
        f"💰 Harga Limit: {harga}\n"
        f"📍 Lokasi: {lokasi}\n"
        f"🗓️ Tanggal: {tgl}\n\n"
        f"🔗 {url}"
    )

def send_lot(session, lot):
    """Ambil detail lalu kirim ke Telegram"""
    lot_id = str(lot.get("lotLelangId") or lot.get("id"))
    if not lot_id:
        return False
    detail = fetch_detail(session, lot_id)
    if not detail:
        return False
    msg = format_lot(detail)
    return send_to_telegram(msg)
