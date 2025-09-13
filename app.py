import requests
import json
import os
import datetime
import telegram
from telegram import InputMediaPhoto

# Konfigurasi
API_URL = "https://example.com/api"  # ganti dengan API asli
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = telegram.Bot(token=TELEGRAM_TOKEN)
SEEN_FILE = "seen_api.json"


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            try:
                return set(json.load(f))
            except:
                return set()
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def fetch_data():
    try:
        print("[INFO] Mulai cek API...", flush=True)
        r = requests.get(API_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        print(f"[DEBUG] Status API: {r.status_code}", flush=True)
        print(f"[DEBUG] Respon mentah (200 char): {r.text[:200]}", flush=True)

        data = r.json().get("data", [])
        print(f"[INFO] Ditemukan {len(data)} lot di API", flush=True)
        return data
    except Exception as e:
        import traceback
        print(f"[ERROR] Gagal ambil data API: {e}", flush=True)
        traceback.print_exc()
        return []


def send_to_telegram(lot):
    lot_id = lot.get("id")
    title = lot.get("title", "Tanpa Judul")
    lokasi = lot.get("lokasi", "Tidak diketahui")
    images = lot.get("images", [])

    caption = f"Lot baru: {title}\nLokasi: {lokasi}"

    if images:
        media_group = []
        for i, img_url in enumerate(images[:5]):
            try:
                file_url = f"{img_url}"
                if i == 0:
                    media_group.append(InputMediaPhoto(media=file_url, caption=caption))
                else:
                    media_group.append(InputMediaPhoto(media=file_url))
            except Exception as e:
                print(f"[WARN] Gagal parse gambar: {e}", flush=True)

        try:
            bot.send_media_group(chat_id=CHAT_ID, media=media_group)
            print(f"[INFO] ✅ Terkirim lot {lot_id} dengan album foto", flush=True)
        except Exception as e:
            print(f"[WARN] Gagal kirim album, fallback caption: {e}", flush=True)
            bot.send_message(chat_id=CHAT_ID, text=caption)
    else:
        bot.send_message(chat_id=CHAT_ID, text=caption)
        print(f"[INFO] ✅ Terkirim lot {lot_id} tanpa gambar", flush=True)


def main():
    print(f"[{datetime.datetime.now()}] Bot mulai jalan...", flush=True)

    seen = load_seen()
    print(f"[DEBUG] Jumlah lot yang sudah pernah dikirim: {len(seen)}", flush=True)

    data = fetch_data()
    baru = 0

    for lot in data:
        lot_id = lot.get("id")
        if lot_id not in seen:
            send_to_telegram(lot)
            seen.add(lot_id)
            baru += 1

    save_seen(seen)
    print(f"[INFO] {baru} lot baru terkirim", flush=True)
    print(f"[INFO] Disimpan {len(seen)} lot ke {SEEN_FILE}", flush=True)
    print(f"[{datetime.datetime.now()}] Bot selesai cek.", flush=True)


if __name__ == "__main__":
    main()
