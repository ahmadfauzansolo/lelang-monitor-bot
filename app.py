def main():
    print(f"[{datetime.now()}] Bot mulai jalan...")

    try:
        r = requests.get(API_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        print(f"[DEBUG] Status API: {r.status_code}")
        data = r.json().get("data", [])
        print(f"[DEBUG] Jumlah lot di API: {len(data)}")
        # kalau mau cek isi JSON
        if len(data) == 0:
            print("[DEBUG] Isi respon API:", r.text[:500])  # tampilkan 500 char awal
    except Exception as e:
        print(f"[ERROR] Gagal ambil data dari API: {e}")
        return

    new_count = 0
    for lot in data:
        lot_id = str(lot.get("id"))
        send_message(lot)
        new_count += 1

    print(f"[INFO] {new_count} lot terkirim (test mode, tanpa filter seen)")
    print(f"[{datetime.now()}] Bot selesai cek.")
