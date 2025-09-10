from flask import Flask
import threading, time, requests, json
import os
from dotenv import load_dotenv

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv()  # untuk local .env

app = Flask(__name__)

API_URL = "https://api.lelang.go.id/api/v1/landing-page-kpknl/6705ef6e-f64f-11ed-b3e2-5620a0c2ec5a/katalog-lot-lelang?namakategori[]=Mobil&namakategori[]=Motor"
KEYWORD_INSTANSI = os.getenv("KEYWORD_INSTANSI", "KPKNL Surakarta").lower()
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "1800"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEEN_FILE = "seen_api.json"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# -----------------------------
# HELPERS
# -----------------------------
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(s):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(s), f, ensure_ascii=False, indent=2)

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
    return res.status_code == 200

# -----------------------------
# MONITOR FUNCTION
# -----------------------------
def monitor_lelang():
    s
