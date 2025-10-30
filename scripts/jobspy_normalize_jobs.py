import os, glob, json, requests

DATA_LAKE = os.environ.get("DATA_LAKE_ROOT", "./ops/datalake")
RAW_DIR = os.path.join(DATA_LAKE, "raw", "jobs")
API = os.environ.get("API_URL", "http://localhost:8000")

def map_row(row):
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

def main():
    files = glob.glob(os.path.join(RAW_DIR, "jobspy_*.jsonl"))
    sent = 0
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                payload = map_row(row)
                r = requests.post(f"{API}/jobs/ingest", json=payload, timeout=30)
                if r.status_code == 200:
                    sent += 1
    print("Ingested:", sent)

if __name__ == "__main__":
    main()
