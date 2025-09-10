import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN") or "8004194993:AAG4Dm-kJ63AIrpf_CWz8sGxF39Dm725weE"
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "418103862"

msg = "Halo! Ini tes dari Bot Lelang Monitor 🚀"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
res = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
print(res.status_code, res.text)
