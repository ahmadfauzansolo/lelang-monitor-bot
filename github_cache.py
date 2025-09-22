import requests
import os
import base64

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ahmadfauzansolo/berita-otomotif-ev")
SEEN_FILE = "seen_api.json"


def get_file_url():
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SEEN_FILE}"


def load_seen():
    """Ambil isi seen_api.json dari GitHub, return list ID."""
    url = get_file_url()
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        content = r.json()
        data = base64.b64decode(content["content"]).decode("utf-8")
        return data.strip().splitlines() if data.strip() else []
    else:
        print(f"[WARN] Tidak bisa load {SEEN_FILE}, status {r.status_code}")
        return []


def save_seen(seen_list):
    """Update seen_api.json di GitHub."""
    url = get_file_url()
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    get_resp = requests.get(url, headers=headers)
    sha = get_resp.json()["sha"] if get_resp.status_code == 200 else None

    data = "\n".join(seen_list)
    encoded = base64.b64encode(data.encode("utf-8")).decode("utf-8")

    payload = {
        "message": "Update seen_api.json",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)
    if r.status_code in (200, 201):
        print("[INFO] seen_api.json berhasil disimpan ke GitHub")
    else:
        print(f"[ERROR] Gagal save seen_api.json, status {r.status_code}, {r.text}")
