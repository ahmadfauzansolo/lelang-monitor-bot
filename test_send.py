import requests
import os

msg = "Halo! Ini tes dari Bot Lelang Monitor 🚀"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
res = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
print(res.status_code, res.text)
