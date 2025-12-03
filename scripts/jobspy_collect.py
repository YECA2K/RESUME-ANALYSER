import os
import argparse
from datetime import datetime, timedelta
import pandas as pd
from jobspy import scrape_jobs

# --------------------------------------------------
# CONFIG DOSSIER DATALAKE
# --------------------------------------------------
DATA_LAKE = os.environ.get("DATA_LAKE_ROOT", "/workspace/datalake")
RAW_DIR = os.path.join(DATA_LAKE, "raw", "jobs")
os.makedirs(RAW_DIR, exist_ok=True)

# --------------------------------------------------
# MOTS-CLÉS / PROFILS IT POUR LE SCRAPING
# --------------------------------------------------
IT_SEARCH_TERMS = [
    "data engineer",
    "data scientist",
    "data analyst",
    "bi engineer",
    "bi developer",
    "machine learning engineer",
    "ml engineer",
    "ai engineer",
    "cloud engineer",
    "cloud architect",
    "devops engineer",
    "site reliability engineer",
    "sre",
    "backend developer",
    "frontend developer",
    "fullstack developer",
    "full stack developer",
    "python developer",
    "java developer",
    "software engineer",
    "software developer",
    "ingénieur systèmes",
    "ingénieur systèmes et réseaux",
    "administrateur systèmes et réseaux",
    "cybersecurity engineer",
    "ingénieur cybersécurité",
    "analyste cybersécurité",
    "ingénieur data",
    "ingénieur informatique",
]

# Keywords IT pour filtrage sur titre + description
TITLE_IT_KEYWORDS = [
    "data engineer", "data scientist", "data analyst",
    "data", "engineer", "ingénieur", "ingenieur",
    "developer", "développeur", "developpeur",
    "devops", "architect", "architecte",
    "scientist", "analyst", "analyste",
    "fullstack", "full stack", "backend", "frontend",
    "sre", "sysadmin", "site reliability",
    "administrateur système", "administrateur systeme",
    "cloud engineer", "cloud architect",
    "consultant data", "consultant bi",
    "bi engineer", "bi developer",
    "ml engineer", "machine learning engineer",
    "ai engineer", "software engineer",
    "software developer", "ingénieur logiciel",
    "ingénieur systèmes", "ingénieur systèmes et réseaux",
    "cybersecurity", "cybersécurité", "sécurité informatique",
    "devsecops", "dev sec ops",
]

TEXT_IT_KEYWORDS = [
    # langages
    "python", "java", "javascript", "typescript",
    "node.js", "nodejs", "node js",
    "c#", "csharp", ".net", "dotnet",
    "c++", "golang", "go lang", "rust",
    "php", "ruby", "scala", "kotlin",
    " r ",  # éviter faux positifs

    # data / sql / bdd
    "sql", "postgres", "postgresql", "mysql", "mariadb", "oracle",
    "mongodb", "mongo db", "mongo-db", "redis", "snowflake",
    "bigquery", "big query", "redshift", "synapse",
    "data warehouse", "datawarehouse", "data lake", "datalake",

    # outils / devops / cloud
    "docker", "kubernetes", "k8s",
    "git", "github", "gitlab", "bitbucket",
    "terraform", "ansible",
    "airflow", "dbt", "spark", "hadoop", "kafka",
    "rest api", "restful", "microservices", "grpc",
    "serverless", "lambda", "ecs", "eks", "gke",
    "aws", "amazon web services", "azure", "gcp", "google cloud",

    # data science / stats
    "machine learning", "deep learning",
    "pandas", "numpy", "scikit-learn", "sklearn",
    "statistique", "statistiques", "statistics",
    "probabilité", "probabilités", "probability",
    "modélisation", "modelisation", "modélisation statistique",
    "feature engineering", "régression", "classification",
    "nlp", "natural language processing",

    # sécurité
    "pentest", "pentester", "penetration testing",
    "owasp", "iso 27001", "rgpd", "siem", "soc",

    # infra
    "linux", "unix", "bash", "shell scripting",
    "système et réseaux", "systèmes et réseaux",
]


def cleanup_old_files(keep_days: int = 10):
    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    for fp in os.listdir(RAW_DIR):
        if fp.endswith(".jsonl"):
            fpath = os.path.join(RAW_DIR, fp)
            if os.path.getmtime(fpath) < cutoff.timestamp():
                print(f"[CLEANUP] Removing old file: {fpath}")
                os.remove(fpath)


def is_it_row(row) -> bool:
    """
    Filtre IT côté scraping :
    - check titre + description avec keywords IT
    """
    title = str(row.get("title", "") or "")
    desc = str(row.get("description", "") or "")
    text = f"{title} {desc}".lower()

    if not text.strip():
        return False

    for kw in TITLE_IT_KEYWORDS:
        if kw.lower() in title.lower():
            return True

    for kw in TEXT_IT_KEYWORDS:
        if kw.lower() in text:
            return True

    return False


def filter_it(df: pd.DataFrame) -> pd.DataFrame:
    if "title" not in df.columns:
        return df.iloc[0:0]

    if "description" not in df.columns:
        df["description"] = ""

    mask = df.apply(is_it_row, axis=1)
    return df[mask]


def main():
    parser = argparse.ArgumentParser()
    # 👉 pour le seed initial : --days 30
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max_per_call", type=int, default=400)  # par (term,location)
    parser.add_argument("--max_total", type=int, default=20000)
    parser.add_argument("--keep_days", type=int, default=10)
    parser.add_argument("--min_it_jobs", type=int, default=3000)
    args = parser.parse_args()

    sites = ["indeed"]  # stable en France, google bloque ton IP de toute façon

    locations = [
        "France",
        "Paris",
        "Lyon",
        "Marseille",
        "Toulouse",
        "Bordeaux",
        "Lille",
        "Nice",
        "Nantes",
        "Strasbourg",
        "Rennes",
        "Remote",
    ]

    hours = args.days * 24

    print(f"[INFO] Scraping with hours_old={hours}")
    print(f"[INFO] Sites: {sites}")
    print(f"[INFO] Locations: {locations}")
    print(f"[INFO] Search terms IT: {IT_SEARCH_TERMS}")

    all_jobs_global = []
    per_site_frames = {s: [] for s in sites}

    for site in sites:
        for term in IT_SEARCH_TERMS:
            for loc in locations:
                try:
                    print(f"[INFO] Scraping {site} @ {loc} – term='{term}'")

                    df_site = scrape_jobs(
                        site_name=[site],
                        search_term=term,
                        location=loc,
                        results_wanted=args.max_per_call,
                        hours_old=hours,
                        country_indeed="France",
                        description_format="markdown",
                    )

                except Exception as e:
                    print(f"[ERROR] {site} failed for {loc} (term='{term}'): {e}")
                    continue

                if df_site is None or df_site.empty:
                    print(f"[WARN] No jobs for {site} @ {loc} with term='{term}'")
                    continue

                before = len(df_site)
                df_site = filter_it(df_site)
                after = len(df_site)
                print(f"[INFO] {site} @ {loc} term='{term}' → {after}/{before} IT jobs")

                if df_site.empty:
                    continue

                per_site_frames[site].append(df_site)
                all_jobs_global.append(df_site)

        # résumé site
        if per_site_frames[site]:
            df_site_all = pd.concat(per_site_frames[site], ignore_index=True)
            print(f"[INFO] {site}: {len(df_site_all)} IT jobs collectés (avant dédoublonnage)")
        else:
            print(f"[WARN] Aucun job IT collecté pour {site}")

    if not all_jobs_global:
        print("[WARN] No jobs collected from any site/location")
        return

    df = pd.concat(all_jobs_global, ignore_index=True)
    print(f"[INFO] Total jobs AVANT dédoublonnage: {len(df)}")

    # Dédoublonnage URL
    if "job_url" in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset=["job_url"])
        after = len(df)
        print(f"[INFO] URLs uniques: {df['job_url'].nunique()}")
        print(f"[INFO] Doublons supprimés (même job_url): {before - after}")

    # Dédoublonnage (site,title,company,location)
    dedup_cols = [c for c in ["site", "title", "company", "location"] if c in df.columns]
    if dedup_cols:
        before = len(df)
        df = df.drop_duplicates(subset=dedup_cols)
        after = len(df)
        print(f"[INFO] Doublons supprimés (combinaison {dedup_cols}): {before - after}")

    # Limite globale
    if len(df) > args.max_total:
        df = df.sample(args.max_total, random_state=42)
        print(f"[INFO] Échantillonnage aléatoire à max_total={args.max_total}")

    # Check de volume IT minimal
    if len(df) < args.min_it_jobs:
        print(f"[WARN] Seulement {len(df)} jobs IT après dédoublonnage (< {args.min_it_jobs})")

    if "site" in df.columns:
        print("[INFO] Jobs par site APRÈS dédoublonnage :")
        print(df["site"].value_counts())

    print(f"[FINAL] Total jobs sauvegardés: {len(df)}")

    out_file = os.path.join(RAW_DIR, "jobspy_all.jsonl")
    df.to_json(out_file, orient="records", lines=True, force_ascii=False)
    print(f"[FINAL] Saved {len(df)} jobs into {out_file}")

    cleanup_old_files(args.keep_days)
    print("[DONE]")


if __name__ == "__main__":
    main()
