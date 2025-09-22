#!/usr/bin/env python3
"""
app.py - BOT MONITOR LELANG

Tugas:
- Ambil daftar lot lelang dari API
- Cek mana yang baru (pakai cache di github_cache.py)
- Ambil detail + foto
- Kirim ke Telegram
"""

import os
import logging
from datetime import datetime

from github_cache import load_seen, save_seen   # <== pakai cache dari file terpisah
from core import make_session, fetch_list, send_lot   # <== semua logic berat di core.py

# Logging format rapi
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def main():
    logger.info("=== BOT LELANG JALAN ===")

    session = make_session()
    lots = fetch_list(session)
    if not lots:
        logger.warning("Tidak ada lot ditemukan, selesai.")
        return

    # Ambil cache lot yang sudah dikirim
    seen = load_seen()
    logger.info(f"Cache berisi {len(seen)} lot sebelumnya")

    new_lots = []
    for lot in lots:
        lot_id = str(lot.get("lotLelangId") or lot.get("id"))
        if not lot_id:
            continue
        if lot_id not in seen:
            new_lots.append(lot)

    if not new_lots:
        logger.info("Tidak ada lot baru.")
        return

    logger.info(f"Ditemukan {len(new_lots)} lot baru")

    for lot in new_lots:
        lot_id = str(lot.get("lotLelangId") or lot.get("id"))
        try:
            ok = send_lot(session, lot)
            if ok:
                seen.add(lot_id)
                logger.info(f"Lot {lot_id} ✅ terkirim")
            else:
                logger.warning(f"Lot {lot_id} ❌ gagal terkirim")
        except Exception as e:
            logger.error(f"Error saat kirim lot {lot_id}: {e}")

    # Simpan update cache
    save_seen(seen)
    logger.info("Cache diperbarui")

if __name__ == "__main__":
    main()
