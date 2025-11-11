import os, glob, json, requests, math

# Définition des chemins
DATA_LAKE = os.environ.get("DATA_LAKE_ROOT", "./ops/datalake")
RAW_DIR = os.path.join(DATA_LAKE, "raw", "jobs")
API_URL = "http://resume-analyser-api-1:8000"

def map_row(row):
    """Transforme une ligne brute en format normalisé."""
    loc = {"city": None, "country": None, "remote": None}
    if isinstance(row.get("location"), str):
        city = row["location"].split(",")[0].strip()
        loc["city"] = city or None
    if row.get("is_remote") is True:
        loc["remote"] = "full"
    return {
        "source": (row.get("site") or "jobspy"),
        "url": row.get("job_url"),
        "title": row.get("title") or "unknown",
        "company": row.get("company"),
        "location": loc,
        "contract_type": row.get("job_type"),
        "seniority": None,
        "skills_required": [],
        "skills_nice": [],
        "description_text": row.get("description") or "",
        "collected_at": str(row.get("date_posted") or ""),
    }

def clean_payload(payload):
    """Nettoie les NaN et valeurs infinies dans le payload JSON."""
    for k, v in payload.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            payload[k] = None
        elif isinstance(v, dict):
            payload[k] = clean_payload(v)
        elif isinstance(v, list):
            payload[k] = [
                None if (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else x
                for x in v
            ]
    return payload

def main():
    files = glob.glob(os.path.join(RAW_DIR, "jobspy_*.jsonl"))
    if not files:
        files = glob.glob(os.path.join(RAW_DIR, "jobspy_all.jsonl"))

    sent = 0
    skipped = 0

    for fp in files:
        print(f"[INFO] Lecture du fichier: {fp}")
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
    print(f"[DONE] Ingested: {sent} lignes, Skipped: {skipped} lignes")

if __name__ == "__main__":
    main()
