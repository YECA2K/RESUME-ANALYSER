# api/app/main.py
import os, datetime
from typing import List, Union
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from pypdf import PdfReader
from .db import db, ensure_indexes
from .schemas import CandidateIn, JobPostingIn, Location
import re

DATA_LAKE = os.environ.get("DATA_LAKE_ROOT", "/app/ops/datalake")

app = FastAPI(title="All-in-One DE Backend")
ensure_indexes()

# ---- Health ----
@app.get("/health")
def health():
    db.command("ping")
    return {"status": "ok"}


# ===========================================================
#                     UPLOAD CV
# ===========================================================
@app.post("/upload_cv")
async def upload_cv(
    file: UploadFile = File(...),
    full_name: str = Form("Unknown"),
    email: str = Form(None),
    city: str = Form(None),
    country: str = Form(None),
):
    raw_cv_dir = os.path.join(DATA_LAKE, "raw", "cv")
    os.makedirs(raw_cv_dir, exist_ok=True)

    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    raw_pdf_path = os.path.join(raw_cv_dir, f"{ts}_{file.filename}")

    with open(raw_pdf_path, "wb") as f:
        f.write(await file.read())

    # Extract text
    text = ""
    try:
        reader = PdfReader(raw_pdf_path)
        for page in reader.pages:
            text += page.extract_text() or ""
    except:
        text = ""

    txt_dir = os.path.join(DATA_LAKE, "raw", "cv_text")
    os.makedirs(txt_dir, exist_ok=True)
    txt_path = os.path.join(txt_dir, f"{ts}_{os.path.splitext(file.filename)[0]}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    skills = []
    for kw in ["python","sql","spark","airflow","aws","azure","gcp","docker",
               "kubernetes","pyspark","etl","pandas"]:
        if re.search(rf"\b{kw}\b", text.lower()):
            skills.append(kw)

    cand_doc = {
        "full_name": full_name,
        "email": email,
        "location": {"city": city, "country": country},
        "skills_declared": sorted(set(skills)),
        "experiences": [],
        "education": [],
        "languages": [],
        "profile_source": "cv",
        "profile_created_at": datetime.datetime.utcnow().isoformat(),
        "cv_pdf_path": raw_pdf_path,
        "cv_text_path": txt_path,
    }
    res = db.candidates.insert_one(cand_doc)
    return {"candidate_id": str(res.inserted_id), "skills_detected": cand_doc["skills_declared"]}


# ===========================================================
#                     CREATE MANUAL CANDIDATE
# ===========================================================
@app.post("/candidates")
def create_candidate(payload: CandidateIn):
    doc = payload.model_dump()
    doc["profile_created_at"] = datetime.datetime.utcnow().isoformat()
    res = db.candidates.insert_one(doc)
    return {"_id": str(res.inserted_id)}


# ===========================================================
#                    BULK + SINGLE JOB INGEST
# ===========================================================
@app.post("/jobs/ingest")
def ingest_job(payload: Union[JobPostingIn, List[JobPostingIn]] = Body(...)):
    def one_upsert(doc: dict):
        doc["ingested_at"] = datetime.datetime.utcnow().isoformat()

        if doc.get("url"):
            key = {"source": doc["source"], "url": doc["url"]}
        else:
            key = {
                "source": doc.get("source"),
                "title": doc.get("title"),
                "company": doc.get("company"),
            }
        db.job_postings.update_one(key, {"$set": doc}, upsert=True)

    try:
        # ---------- BULK ----------
        if isinstance(payload, list):
            for item in payload:
                one_upsert(item.model_dump())
            return {"status": "ok", "ingested": len(payload)}

        # ---------- SINGLE ----------
        one_upsert(payload.model_dump())
        return {"status": "ok", "ingested": 1}

    except Exception as e:
        raise HTTPException(400, f"ingest error: {e}")


# ===========================================================
#                     MATCHING ENGINE
# ===========================================================
def recall_topk(job, k=100):
    terms = job.get("skills_required", []) + (job.get("title") or "").split()
    query = " ".join(terms)
    if not query.strip():
        return list(db.candidates.find({}).limit(k))
    return list(db.candidates.find({"$text": {"$search": query}}).limit(k))

def llm_score_stub(job, cand):
    req = {s.lower() for s in job.get("skills_required", [])}
    have = {s.lower() for s in cand.get("skills_declared", [])}
    matched = sorted(list(req & have))
    missing = sorted(list(req - have))
    base = len(matched) / (len(req) or 1)
    score = round(base * 0.9, 3)
    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "rationale": f"{len(matched)} compétences sur {len(req)}"
    }

@app.post("/match/run")
def run_match(job_title: str, top_k: int = 100, top_n: int = 10):
    job = db.job_postings.find_one({"title": job_title})
    if not job:
        raise HTTPException(404, "job not found")

    cands = recall_topk(job, k=top_k)
    results = []

    for c in cands:
        res = llm_score_stub(job, c)
        results.append({
            "job_ref": str(job["_id"]),
            "candidate_ref": str(c["_id"]),
            **res
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    db.matches.insert_many([
        {
            "job_ref": r["job_ref"],
            "candidate_ref": r["candidate_ref"],
            "score": r["score"],
            "rationale_json": r,
            "matched_at": datetime.datetime.utcnow().isoformat()
        }
        for r in results[:top_n]
    ])

    return {"job_title": job_title, "matched": len(results[:top_n])}


@app.get("/match")
def get_match(job_title: str, k: int = 10):
    job = db.job_postings.find_one({"title": job_title})
    if not job:
        raise HTTPException(404, "job not found")

    cur = db.matches.find({"job_ref": str(job["_id"])}).sort("score", -1).limit(k)
    return {"items": list(cur)}
