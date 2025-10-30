import os, argparse, json
from datetime import date
import pandas as pd
from jobspy import scrape_jobs

DATA_LAKE = os.environ.get("DATA_LAKE_ROOT", "./ops/datalake")
RAW_DIR = os.path.join(DATA_LAKE, "raw", "jobs")
os.makedirs(RAW_DIR, exist_ok=True)

def _csv(s: str):
    parts = [t for t in (s or "").split(",")]
    return [p.strip() for p in parts if p is not None]

def _existing_urls(jsonl_path: str) -> set:
    urls = set()
    if not os.path.isfile(jsonl_path):
        return urls
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                u = json.loads(line).get("job_url")
                if u:
                    urls.add(u)
            except Exception:
                continue
    return urls

def _append_jsonl(jsonl_path: str, df: pd.DataFrame):
    with open(jsonl_path, "a", encoding="utf-8") as f:
        for rec in df.to_dict(orient="records"):
            # Convert non-serializable objects (dates, timestamps) to strings
            for k, v in rec.items():
                if hasattr(v, "isoformat"):
                    rec[k] = v.isoformat()
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser("JobSpy Indeed collector (24h, append, dedup)")
    p.add_argument("--queries", default=(
        " ,engineer,developer,manager,architect,cloud,ai,data,hr,finance,"
        "marketing,sales,security,analyst,consultant,full stack,frontend,"
        "backend,devops,product,project"
    ))
    p.add_argument("--locations", default="France,Remote,Paris,Lyon")
    p.add_argument("--countries", default="france,uk,germany,spain,italy,netherlands,belgium,usa,canada")
    p.add_argument("--sites", default="indeed", help="Keep for compatibility")
    p.add_argument("--pages", type=int, default=3)
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--outfile", default=f"jobspy_all.jsonl")
    p.add_argument("--append", type=int, default=1)
    args = p.parse_args()

    queries   = _csv(args.queries)
    locations = _csv(args.locations)
    countries = _csv(args.countries)
    per_site  = min(50 * args.pages, 1000)
    out_path  = os.path.join(RAW_DIR, args.outfile)

    print(f"[INFO] Output file: {out_path}")
    parts = []

    for q in queries:
        for loc in locations:
            for country in countries:
                try:
                    df = scrape_jobs(
                        site_name=["indeed"],
                        search_term=q,
                        location=loc,
                        results_wanted=per_site,
                        hours_old=args.days * 24,
                        country_indeed=country,
                        description_format="markdown",  # include job descriptions
                    )
                    if df is None or df.empty:
                        print(f"[WARN] 0 rows for '{q or '(all)'}' @ {loc} ({country})")
                        continue
                    parts.append(df)
                    print(f"[OK] {len(df)} rows for '{q or '(all)'}' @ {loc} ({country})")
                except Exception as e:
                    print(f"[ERROR] {e}")

    if not parts:
        print("No results.")
        return

    new_df = pd.concat(parts, ignore_index=True)
    if "job_url" in new_df.columns:
        before = len(new_df)
        new_df = new_df.drop_duplicates(subset=["job_url"])
        print(f"[BATCH DEDUP] {before} → {len(new_df)} unique")

    if args.append:
        seen = _existing_urls(out_path)
        if seen and "job_url" in new_df.columns:
            new_df = new_df[~new_df["job_url"].isin(seen)]
            print(f"[HIST DEDUP] {len(new_df)} new unique rows vs history")

        if len(new_df) == 0:
            print("[APPEND] No new rows to append.")
            return

        tmp = out_path + ".tmp"
        _append_jsonl(tmp, new_df)
        if not os.path.exists(out_path):
            os.replace(tmp, out_path)
        else:
            with open(out_path, "a", encoding="utf-8") as fout, open(tmp, "r", encoding="utf-8") as fin:
                for line in fin:
                    fout.write(line)
            os.remove(tmp)
        print(f"[APPEND] +{len(new_df)} rows → {out_path}")
    else:
        new_df.to_json(out_path, orient="records", lines=True, force_ascii=False)
        print(f"[WRITE] {len(new_df)} rows → {out_path}")

if __name__ == "__main__":
    main()
