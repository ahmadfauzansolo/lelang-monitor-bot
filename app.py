def fetch_lots():
    url = f"{BASE_URL}/kpknl/{KPKNL_ID}/detail-auction/{AUCTION_ID}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        
        lots = data.get("lots", [])
        logging.info(f"Ditemukan {len(lots)} lot di API")

        # DEBUG: tampilkan JSON mentah dari 1 lot pertama
        if lots:
            logging.info("Contoh lot dari API:\n" + json.dumps(lots[0], indent=2, ensure_ascii=False))

        return lots
    except Exception as e:
        logging.error(f"Gagal fetch lots: {e}")
        return []
