import os
import glob
import json
import math
import requests

DATA_LAKE = os.environ.get("DATA_LAKE_ROOT", "/workspace/datalake")
RAW_DIR = os.path.join(DATA_LAKE, "raw", "jobs")
API = os.environ.get("API_URL", "http://api:8000")


def clean_payload(job: dict):
    for k, v in job.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            job[k] = None
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, float) and (math.isnan(vv) or math.isinf(vv)):
                    job[k][kk] = None
    return job


def safe(x):
    return x if isinstance(x, str) else ""


def map_row(row):
    loc_raw = row.get("location")
    loc = {"city": None, "country": None, "remote": None}

    if isinstance(loc_raw, str):
        loc["city"] = loc_raw.split(",")[0].strip()
    elif isinstance(loc_raw, dict):
        loc["city"] = loc_raw.get("city")
        loc["country"] = loc_raw.get("country")

    if row.get("is_remote") in [True, "true", "full", "FULL"]:
        loc["remote"] = "full"

    desc = row.get("description")
    if isinstance(desc, list):
        desc = " ".join(desc)
    if desc is None:
        desc = ""

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


# ==============================
#   FILTRE IT FINAL (Mongo-safe)
# ==============================

TITLE_IT_KEYWORDS = [
    "data engineer", "data scientist", "data analyst",
    "bi engineer", "bi developer",
    "machine learning engineer", "ml engineer", "ai engineer",
    "cloud engineer", "cloud architect",
    "devops engineer", "devops",
    "site reliability engineer", "sre",
    "backend developer", "frontend developer",
    "fullstack developer", "full stack developer",
    "python developer", "java developer",
    "software engineer", "software developer",
    "ingénieur systèmes", "ingenieur systemes",
    "ingénieur systèmes et réseaux", "ingenieur systemes et reseaux",
    "administrateur systèmes et réseaux",
    "administrateur systèmes", "administrateur systemes",
    "cybersecurity engineer", "cyber security", "cybersécurité",
    "ingénieur cybersécurité", "sécurité informatique",
    "devsecops", "dev sec ops",
    "data manager", "data architect",
]

TEXT_IT_KEYWORDS = [
    "python", "java", "javascript", "typescript",
    "node.js", "nodejs", "node js",
    "c#", "csharp", ".net", "dotnet",
    "c++", "golang", "go lang", "rust",
    "php", "ruby", "scala", "kotlin",
    " r ",  # éviter faux positifs

    "sql", "postgres", "postgresql", "mysql", "mariadb", "oracle",
    "mongodb", "mongo db", "mongo-db", "redis",
    "snowflake", "bigquery", "big query", "redshift", "synapse",
    "data warehouse", "datawarehouse", "data lake", "datalake",

    "docker", "kubernetes", "k8s",
    "git", "github", "gitlab", "bitbucket",
    "terraform", "ansible",
    "airflow", "dbt", "spark", "hadoop", "kafka",
    "rest api", "restful", "microservices", "grpc",
    "serverless", "lambda", "ecs", "eks", "gke",
    "aws", "amazon web services", "azure", "gcp", "google cloud",

    "machine learning", "deep learning",
    "pandas", "numpy", "scikit-learn", "sklearn",
    "statistique", "statistiques", "statistics",
    "probabilité", "probabilités", "probability",
    "modélisation", "modelisation", "modélisation statistique",
    "feature engineering", "régression", "regression", "classification",
    "nlp", "natural language processing",

    "pentest", "pentester", "penetration testing",
    "owasp", "iso 27001", "rgpd", "siem", "soc",

    "linux", "unix", "bash", "shell scripting",
    "système et réseaux", "systèmes et réseaux",
]


def is_it_job(job: dict) -> bool:
    title = (job.get("title") or "").lower()
    desc = (job.get("description_text") or "").lower()
    text = f"{title} {desc}"

    if not text.strip():
        return False

    for kw in TITLE_IT_KEYWORDS:
        if kw.lower() in title:
            return True

    for kw in TEXT_IT_KEYWORDS:
        if kw.lower() in text:
            return True

    return False


def main():
    files = glob.glob(os.path.join(RAW_DIR, "*.jsonl"))
    if not files:
        print("[ERROR] No files found")
        return

    sent = 0
    skipped = 0

    for fp in files:
        print(f"[INFO] Processing {fp}")

        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    payload = clean_payload(map_row(row))

                    # ⚠️ FILTRE IT FINAL (double sécurité)
                    if not is_it_job(payload):
                        skipped += 1
                        continue

                    res = requests.post(
                        f"{API}/jobs/ingest",
                        json=payload,
                        timeout=10
                    )

                    if res.status_code == 200:
                        sent += 1
                    else:
                        skipped += 1

                except Exception as e:
                    skipped += 1
                    print(f"[WARN] skipped: {e}")

    print(f"[DONE] Ingested {sent}, skipped {skipped}")


if __name__ == "__main__":
    main()
