# =========================================
# MAIN
# =========================================
def main():
    print(f"[{datetime.now()}] Bot mulai jalan...")

    try:
        r = requests.get(API_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json().get("data", [])
    except Exception as e:
        print(f"[ERROR] Gagal ambil data dari API: {e}")
        return

    new_count = 0
    for lot in data:
        lot_id = str(lot.get("id"))

        # kirim semua lot tanpa filter seen
        send_message(lot)
        new_count += 1

    print(f"[INFO] {new_count} lot terkirim (test mode, tanpa filter seen)")
    print(f"[{datetime.now()}] Bot selesai cek.")
