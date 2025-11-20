import os
import glob
import json
import math
import requests

# ✅ Chemin du Data Lake (injecté via Docker-compose)
DATA_LAKE = os.environ.get("DATA_LAKE_ROOT", "/workspace/datalake")
RAW_DIR = os.path.join(DATA_LAKE, "raw", "jobs")

# ✅ API FastAPI interne au Docker-compose
API = os.environ.get("API_URL", "http://api:8000")

def map_row(row):
    """Transforme une ligne brute en format normalisé, robustement."""

    # --- Location ---
    loc_raw = row.get("location")
    loc = {"city": None, "country": None, "remote": None}

    if isinstance(loc_raw, str):
        loc["city"] = loc_raw.split(",")[0].strip()
    elif isinstance(loc_raw, dict):  # jobspy change parfois le format
        loc["city"] = loc_raw.get("city") or None
        loc["country"] = loc_raw.get("country") or None

    if row.get("is_remote") in [True, "true", "full", "FULL"]:
        loc["remote"] = "full"

    # --- Description ---
    desc = row.get("description")
    if isinstance(desc, list):
        desc = " ".join(desc)
    if desc is None:
        desc = ""

    # --- Safe fields ---
    def safe(x):
        return x if isinstance(x, str) else ""

    return {
        "source": safe(row.get("site")) or "jobspy",
        "url": safe(row.get("job_url")),
        "title": safe(row.get("title")) or "Unknown",
        "company": safe(row.get("company")),
        "location": loc,
        "contract_type": safe(row.get("job_type")),
        "seniority": None,
        "skills_required": [],
        "skills_nice": [],
        "description_text": desc,
        "collected_at": safe(str(row.get("date_posted"))),
    }

def main():
    print(f"[INFO] DATA_LAKE = {DATA_LAKE}")
    print(f"[INFO] RAW_DIR = {RAW_DIR}")
    print(f"[INFO] API = {API}")

    # ✅ On charge TOUTES les sources possibles
    files = glob.glob(os.path.join(RAW_DIR, "jobspy_*.jsonl"))
    files += glob.glob(os.path.join(RAW_DIR, "jobspy_all.jsonl"))

    if not files:
        print("[ERROR] ❌ Aucun fichier JSONL trouvé")
        return

    print(f"[INFO] Fichiers trouvés : {files}")

    sent = 0
    skipped = 0

    for fp in files:
        print(f"[INFO] Lecture fichier : {fp}")

        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)

                    payload = map_row(row)
                    payload = clean_payload(payload)

                    r = requests.post(f"{API}/jobs/ingest", json=payload, timeout=30)

                    if r.status_code == 200:
                        sent += 1
                    else:
                        skipped += 1
                        print(f"[WARN] HTTP {r.status_code} pour {payload.get('title')}")

                except Exception as e:
                    skipped += 1
                    print(f"[WARN] Ligne ignorée ({type(e).__name__}): {e}")

    print(f"[DONE] ✅ Ingested: {sent} lignes, Skipped: {skipped} lignes")

if __name__ == "__main__":
    main()
