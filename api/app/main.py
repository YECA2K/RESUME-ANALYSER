import os
import json
import re
import fitz  # PyMuPDF
from typing import Dict, Any, List, Tuple

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from app.db import (
    save_candidate,
    load_last_candidate,
    load_jobs,
    save_job,
    find_top_jobs_by_embedding,
    clean_mongo,
)
from app.llm.extract_cv_openrouter import extract_cv_data
from app.llm.matcher_openrouter import match_candidate_to_jobs
from app.llm.openrouter_client import call_openrouter
from app.llm.embeddings import embed_text
from app.schemas import JobOffer


# ======================================================
# FASTAPI INIT
# ======================================================
app = FastAPI(title="Resume Matcher API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================
# HEALTH
# ======================================================
@app.get("/health")
def health():
    return {"status": "OK"}

# ======================================================
# TEST OPENROUTER
# ======================================================
@app.get("/test_openrouter")
def test_openrouter():
    try:
        resp = call_openrouter(
            model="qwen/qwen-2.5-7b-instruct",
            messages=[{"role": "user", "content": "Réponds uniquement OUI"}],
            max_tokens=10,
        )
        return {"status": "OK", "raw": resp}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


# ======================================================
# PDF → TEXT
# ======================================================
def extract_text_from_pdf(file: UploadFile) -> str:
    """
    Reads PDF in memory and returns raw text.
    """
    try:
        pdf_bytes = file.file.read()
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "".join(page.get_text() for page in pdf)
        pdf.close()
        return text or ""
    except Exception as e:
        raise Exception(f"PDF extraction failed: {e}")


# ======================================================
# CV / NOT-CV GATE (prevents invoices / PC configs)
# ======================================================
def looks_like_cv(text: str) -> bool:
    """
    Fast heuristic gate to reject non-CV documents.
    """
    t = (text or "").lower()

    # too small => not a CV
    if len(t) < 600:
        return False

    cv_keywords = [
        "cv", "curriculum", "profil", "profile",
        "expérience", "experience", "compétences", "competences",
        "formation", "éducation", "education",
        "projet", "projects", "certification",
        "linkedin", "github"
    ]
    invoice_keywords = [
        "prix", "qty", "total", "sous-total", "remise", "reduction",
        "mad", "tva", "facture", "invoice", "produit", "adresse",
        "subtotal", "amount", "order"
    ]

    cv_hits = sum(kw in t for kw in cv_keywords)
    inv_hits = sum(kw in t for kw in invoice_keywords)

    money_tokens = len(re.findall(r"\b\d+([.,]\d+)?\s*(mad|€|eur|\$)\b", t))
    table_tokens = len(re.findall(r"\b(qty|total|prix|produit)\b", t))

    # strong invoice signal
    if inv_hits >= 3 and (money_tokens >= 2 or table_tokens >= 3):
        return False

    return cv_hits >= 2


# ======================================================
# TEXT BUILDERS FOR EMBEDDINGS
# ======================================================
def cv_to_text_for_embedding(cv: dict) -> str:
    """
    Build compact text for embedding: summary + skills + experiences.
    """
    parts = []

    if cv.get("summary"):
        parts.append(str(cv["summary"]))

    skills = cv.get("skills") or []
    if skills:
        parts.append("Skills: " + ", ".join([str(s) for s in skills]))

    for exp in cv.get("experiences", []):
        if isinstance(exp, dict):
            seg = " ".join(
                [
                    exp.get("title", "") or exp.get("position", ""),
                    exp.get("company", ""),
                    exp.get("period", "") or exp.get("years", ""),
                    (exp.get("summary", "") or "")[:220],
                ]
            ).strip()
            if seg:
                parts.append(seg)
        else:
            parts.append(str(exp))

    if not parts:
        parts.append(cv.get("full_name", ""))

    return "\n".join(parts)


def job_to_text_for_embedding(job: dict) -> str:
    parts = []
    if job.get("title"):
        parts.append(job["title"])
    if job.get("company"):
        parts.append(job["company"])
    if job.get("description_text"):
        parts.append(job["description_text"])

    req = job.get("skills_required") or []
    if req:
        parts.append("Required: " + ", ".join(req))

    nice = job.get("skills_nice") or []
    if nice:
        parts.append("Nice: " + ", ".join(nice))

    return "\n".join(parts)


# ======================================================
# NORMALIZE CANDIDATE FOR LLM
# ======================================================
def normalize_candidate(d: dict):
    class Obj:
        pass

    c = Obj()
    for k, v in d.items():
        setattr(c, k, v)

    c.skills = d.get("skills", []) or d.get("skills_detected", [])
    c.experiences = d.get("experiences", [])
    c.summary = d.get("summary", "") or ""
    c.full_name = d.get("full_name", "") or ""

    return c


# ======================================================
# DEDUPE JOBS (prevents repeated offers in output)
# ======================================================
def job_key(job: Dict[str, Any]) -> Tuple[str, str, str]:
    url = (job.get("url") or "").strip().lower()
    if url:
        return (url, "", "")
    title = (job.get("title") or "").strip().lower()
    company = (job.get("company") or "").strip().lower()
    source = (job.get("source") or "").strip().lower()
    return (title, company, source)


def dedupe_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for j in jobs:
        k = job_key(j)
        if k in seen:
            continue
        seen.add(k)
        out.append(j)
    return out


# ======================================================
# TEST CV EXTRACTION
# ======================================================
@app.post("/test_extract")
async def test_extract(file: UploadFile = File(...)):
    try:
        text = extract_text_from_pdf(file)

        if not looks_like_cv(text):
            return {
                "status": "ERROR",
                "detail": "Document does not look like a CV.",
                "candidate": {
                    "full_name": "",
                    "summary": "",
                    "skills": [],
                    "languages": [],
                    "experiences": [],
                    "education": [],
                },
                "raw": "",
            }

        cv = extract_cv_data(text)
        return {
            "status": "OK",
            "candidate": clean_mongo(cv),
            "raw": json.dumps(cv, ensure_ascii=False, indent=2),
        }
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


# ======================================================
# TEST MATCHING (DEBUG)
# ======================================================
@app.get("/test_matching")
def test_matching():
    cand = load_last_candidate()
    if not cand:
        return {"status": "ERROR", "detail": "No candidate in DB"}

    emb_text = cv_to_text_for_embedding(cand)
    cv_emb = embed_text(emb_text)

    jobs = find_top_jobs_by_embedding(cv_emb, top_k=80, max_jobs=int(os.getenv("MATCH_MAX_JOBS", "20000")))
    if not jobs:
        jobs = load_jobs(limit=80)

    jobs = dedupe_jobs(jobs)

    # Rerank on a capped, stable pool
    rerank_pool = jobs[:40]

    candidate_obj = normalize_candidate(cand)
    ranking = match_candidate_to_jobs(candidate_obj, rerank_pool)

    full_matches = []
    for r in ranking:
        try:
            idx = int(r.get("job_index", 0)) - 1
            if 0 <= idx < len(rerank_pool):
                job = rerank_pool[idx].copy()
                job = clean_mongo(job)
                job["score"] = float(r.get("score"))
                full_matches.append(job)
        except Exception:
            continue

    # fallback with embedding similarity
    if not full_matches and jobs:
        for job in jobs[:20]:
            j = clean_mongo(job)
            j["score"] = float(job.get("similarity") or 0.0)
            full_matches.append(j)

    full_matches = dedupe_jobs(full_matches)

    full_matches = sorted(full_matches, key=lambda x: float(x.get("score") or 0.0), reverse=True)

    return {"status": "OK", "candidate": clean_mongo(cand), "matches": full_matches}


# ======================================================
# FULL WORKFLOW — UPLOAD CV
# ======================================================
@app.post("/upload_cv")
async def upload_cv(
    file: UploadFile = File(...),
    full_name: str = Form(""),
):
    """
    1) PDF -> text
    2) CV gate (reject invoices / non-CV)
    3) Extract structured CV via LLM
    4) Save candidate
    5) CV embedding -> retrieve closest jobs by embedding (from ALL jobs with embeddings)
    6) Deduplicate + Stable rerank pool
    7) LLM rerank returns scores
    8) Return full job docs with non-null score
    """
    try:
        # 1) PDF -> text
        text = extract_text_from_pdf(file)

        # 2) Reject non-CV
        if not looks_like_cv(text):
            return {
                "status": "ERROR",
                "detail": "Document does not look like a CV.",
                "candidate": {
                    "full_name": full_name,
                    "summary": "",
                    "skills": [],
                    "languages": [],
                    "experiences": [],
                    "education": [],
                },
                "matches": [],
            }

        # 3) Extract CV
        cv = extract_cv_data(text)
        if full_name and full_name.strip():
            fn = full_name.strip()
            if fn.lower() not in {"enter your name", "your name", "name"}:
                cv["full_name"] = fn

        # 4) Save candidate
        save_candidate(cv)

        # 5) Embedding -> retrieve closest jobs
        emb_text = cv_to_text_for_embedding(cv)
        cv_emb = embed_text(emb_text)

        jobs = find_top_jobs_by_embedding(
            cv_emb,
            top_k=120,
            max_jobs=int(os.getenv("MATCH_MAX_JOBS", "20000")),
        )
        if not jobs:
            jobs = load_jobs(limit=120)

        # 6) Deduplicate + stable rerank pool
        jobs = dedupe_jobs(jobs)
        rerank_pool = jobs[:40]

        # 7) Rerank via LLM
        candidate_obj = normalize_candidate(cv)
        ranking = match_candidate_to_jobs(candidate_obj, rerank_pool)

        full_matches = []
        for r in ranking:
            try:
                idx = int(r.get("job_index", 0)) - 1
                if 0 <= idx < len(rerank_pool):
                    job = rerank_pool[idx].copy()
                    job = clean_mongo(job)
                    job["score"] = float(r.get("score"))
                    full_matches.append(job)
            except Exception:
                continue

        # 8) Fallback: embedding similarity if LLM returns nothing
        if not full_matches and jobs:
            for job in jobs[:20]:
                j = clean_mongo(job)
                j["score"] = float(job.get("similarity") or 0.0)
                full_matches.append(j)

        # Always dedupe output
        full_matches = dedupe_jobs(full_matches)

        # Ensure non-null numeric score
        cleaned = []
        for j in full_matches:
            try:
                j["score"] = float(j.get("score") or 0.0)
                cleaned.append(j)
            except Exception:
                continue
        full_matches = cleaned

        # Sort by score desc
        full_matches = sorted(full_matches, key=lambda x: float(x.get("score") or 0.0), reverse=True)

        return {
            "candidate": clean_mongo(cv),
            "matches": full_matches,
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "detail": str(e),
            "candidate": {
                "full_name": full_name,
                "summary": "",
                "skills": [],
                "languages": [],
                "experiences": [],
                "education": [],
            },
            "matches": [],
        }


# ======================================================
# JOB INGESTION (used by normalize script)
# ======================================================
@app.post("/jobs/ingest")
def ingest_job(job: JobOffer):
    job_dict = job.dict()

    emb_text = job_to_text_for_embedding(job_dict)
    job_dict["embedding"] = embed_text(emb_text)

    save_job(job_dict)
    return {"status": "OK", "upserted": True}


# ======================================================
# TEST LLM DIRECT (debug)
# ======================================================
@app.get("/test_llm_direct")
def test_llm_direct():
    system_prompt = "You are a job-matching AI. Return JSON only."
    user_prompt = """
Candidate:
Skills = ["Python", "AWS", "Airflow"]
Experiences = ["Data Engineer 3 years"]

Job:
Title: Python Data Engineer
Description: Looking for Python, ETL, Airflow, AWS.

Return ONLY JSON:
[
  {"job_index": 1, "score": 0.90}
]
"""
    result = call_openrouter(
        model="qwen/qwen-2.5-7b-instruct",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=100,
    )

    try:
        parsed = json.loads(result)
        return {"status": "OK", "raw": result, "parsed": parsed}
    except Exception:
        return {"status": "RAW_ONLY", "raw": result}
