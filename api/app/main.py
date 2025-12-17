# api/app/main.py
from __future__ import annotations

import os
import json
import re
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from app.db import (
    save_candidate,
    load_last_candidate,
    save_job,
    find_top_jobs_by_embedding,
    clean_mongo,
    dedup_jobs_by_url,
    ensure_indexes,
)
from app.llm.extract_cv_openrouter import extract_cv_data
from app.llm.matcher_openrouter import match_candidate_to_jobs
from app.llm.openrouter_client import call_openrouter
from app.llm.embeddings import embed_text
from app.schemas import JobOffer

USE_LLM_RERANK = os.getenv("USE_LLM_RERANK", "0").strip() == "1"
EMBED_TOPK = int(os.getenv("EMBED_TOPK", "80"))     # candidates for rerank (or final results)
RETURN_TOPK = int(os.getenv("RETURN_TOPK", "20"))   # what frontend displays
NON_IT_THRESHOLD = float(os.getenv("NON_IT_THRESHOLD", "0.60"))  # score in [0,1]


app = FastAPI(title="Resume Matcher API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    ensure_indexes()


@app.get("/health")
def health():
    return {
        "status": "OK",
        "use_llm_rerank": USE_LLM_RERANK,
        "non_it_threshold": NON_IT_THRESHOLD,
    }


@app.get("/test_openrouter")
def test_openrouter():
    try:
        resp = call_openrouter(
            model="qwen/qwen-2.5-7b-instruct",
          #  model="qwen/qwen3-coder:free",
            messages=[{"role": "user", "content": "Réponds uniquement OUI"}],
            max_tokens=10,
        )
        return {"status": "OK", "raw": resp}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


def extract_text_from_pdf(file: UploadFile) -> str:
    try:
        pdf = fitz.open(stream=file.file.read(), filetype="pdf")
        text = "".join(page.get_text() for page in pdf)
        pdf.close()
        return text
    except Exception as e:
        raise Exception(f"PDF extraction failed: {e}")


def cv_to_text_for_embedding(cv: dict) -> str:
    """
    Build the text that will be embedded for the candidate.

    IMPORTANT:
    - We do NOT embed the full summary (it can talk about 'Master Data Engineering' etc.).
    - We focus on explicit skills + concrete experiences.
    """
    parts = []

    skills = cv.get("skills") or cv.get("skills_detected") or []
    if skills:
        parts.append("Compétences principales: " + ", ".join(skills))

    for exp in cv.get("experiences", []):
        if isinstance(exp, dict):
            seg = " ".join(
                [
                    exp.get("title", "") or exp.get("position", ""),
                    exp.get("company", ""),
                    exp.get("period", "") or exp.get("years", ""),
                    (exp.get("summary", "") or "")[:200],
                ]
            ).strip()
            if seg:
                parts.append(seg)
        else:
            parts.append(str(exp))

    if not parts:
        if cv.get("full_name"):
            parts.append(cv["full_name"])
        if cv.get("summary"):
            parts.append(cv["summary"])

    return "\n".join(parts).strip()


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

    return "\n".join(parts).strip()


def normalize_candidate(d: dict):
    class Obj:
        pass

    c = Obj()
    for k, v in d.items():
        setattr(c, k, v)

    c.skills = d.get("skills", []) or d.get("skills_detected", [])
    c.experiences = d.get("experiences", [])
    c.summary = d.get("summary", "")
    c.full_name = d.get("full_name", "")
    return c


def looks_like_cv(cv: dict) -> bool:
    """
    Simple quality gate to prevent 'PC invoice PDF' etc. from producing matches.
    You can tune it later.
    """
    full_name = (cv.get("full_name") or "").strip()
    summary = (cv.get("summary") or "").strip()
    skills = cv.get("skills") or []
    exp = cv.get("experiences") or []
    edu = cv.get("education") or []

    signal = 0
    if len(full_name) >= 4:
        signal += 1
    if len(summary.split()) >= 10:
        signal += 1
    if len(skills) >= 3:
        signal += 1
    if len(exp) >= 1:
        signal += 1
    if len(edu) >= 1:
        signal += 1

    return signal >= 2  # allow minimal CVs but block junk


# -------------------------------------------------------
# Skill overlap + domain detection (same as before)
# -------------------------------------------------------
def _normalize_skill(s: str) -> str:
    return (s or "").strip().lower()


def _skill_overlap(candidate: dict, job: dict) -> float:
    cand_skills = {_normalize_skill(s) for s in (candidate.get("skills") or []) if _normalize_skill(s)}
    if not cand_skills:
        return 0.0

    job_skills = []
    for key in ("skills_required", "skills_nice"):
        for s in job.get(key) or []:
            ns = _normalize_skill(s)
            if ns:
                job_skills.append(ns)

    job_set = set(job_skills)
    if not job_set:
        return 0.0

    inter = cand_skills & job_set
    if not inter:
        return 0.0

    recall = len(inter) / len(job_set)
    return float(recall)


RESTO_KEYWORDS = [
    "restauration", "restaurant", "resto", "serveur", "serveuse",
    "service en salle", "service au comptoir", "snacking", "snack",
    "cuisine", "cuisinier", "plonge", "fast food", "sandwicherie",
    "hôtellerie", "hotel", "hôtel", "haccp", "mcdonald", "mcdo",
    "burger king", "kfc", "quick"
]

IT_DATA_KEYWORDS = [
    "data", "python", "sql", "power bi", "powerbi", "tableau",
    "cloud", "aws", "azure", "gcp", "big data", "spark", "etl",
    "machine learning", "deep learning", "analyste données",
    "data engineer", "data scientist", "développeur", "developer",
    "ingénieur logiciel", "software engineer"
]

MARKETING_KEYWORDS = [
    "marketing", "campagne", "seo", "sea", "référencement",
    "campagnes", "social media", "réseaux sociaux", "crm",
    "fidélisation", "acquisition client", "emailing"
]


def _detect_domains_from_text(text: str) -> set[str]:
    t = (text or "").lower()
    domains: set[str] = set()

    if any(w in t for w in RESTO_KEYWORDS):
        domains.add("restauration")
    if any(w in t for w in IT_DATA_KEYWORDS):
        domains.add("it_data")
    if any(w in t for w in MARKETING_KEYWORDS):
        domains.add("marketing")

    return domains


def _candidate_domain_text(cv: dict) -> str:
    parts = []
    for exp in cv.get("experiences", []):
        if isinstance(exp, dict):
            for k in ("title", "summary", "company"):
                v = exp.get(k)
                if v:
                    parts.append(str(v))
        else:
            parts.append(str(exp))
    return " ".join(parts)


@app.post("/test_extract")
async def test_extract(file: UploadFile = File(...)):
    try:
        text = extract_text_from_pdf(file)
        cv = extract_cv_data(text)
        return {
            "status": "OK",
            "candidate": clean_mongo(cv),
            "is_cv": looks_like_cv(cv),
            "raw": json.dumps(cv, ensure_ascii=False, indent=2),
        }
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


@app.get("/test_matching")
def test_matching():
    cand = load_last_candidate()
    if not cand:
        return {"status": "ERROR", "detail": "No candidate in DB"}

    emb_text = cv_to_text_for_embedding(cand)
    cv_emb = embed_text(emb_text)

    jobs = find_top_jobs_by_embedding(cv_emb, top_k=EMBED_TOPK)
    jobs = dedup_jobs_by_url(jobs)

    matches = _rank_jobs(cand, jobs)
    return {"status": "OK", "candidate": clean_mongo(cand), "matches": matches}


def _rank_jobs(candidate_dict: dict, jobs: list[dict]) -> list[dict]:
    """
    Final scoring: similarity + skill overlap + rough domain match.
    """
    if not jobs:
        return []

    cand_domain_text = _candidate_domain_text(candidate_dict)
    candidate_domains = _detect_domains_from_text(cand_domain_text)

    for j in jobs:
        j["_overlap_score"] = _skill_overlap(candidate_dict, j)

        job_text = " ".join(
            [
                str(j.get("title") or ""),
                str(j.get("description_text") or ""),
                str(j.get("contract_type") or ""),
            ]
        )
        job_domains = _detect_domains_from_text(job_text)
        j["_domains"] = job_domains

        if candidate_domains and job_domains:
            inter = candidate_domains & job_domains
            j["_domain_score"] = float(len(inter) / len(job_domains))
        else:
            j["_domain_score"] = 0.0

    if candidate_domains:
        domain_matched = [j for j in jobs if j["_domain_score"] > 0.0]
    else:
        domain_matched = []

    if domain_matched:
        base_jobs = domain_matched
    else:
        base_jobs = jobs

    def sim_key(j):
        sim = j.get("similarity")
        try:
            sim = float(sim) if sim is not None else 0.0
        except Exception:
            sim = 0.0
        tie = str(j.get("url") or j.get("_id") or "")
        return (sim, tie)

    base_sorted = sorted(base_jobs, key=sim_key, reverse=True)

    SIM_WEIGHT = 0.6
    OVERLAP_WEIGHT = 0.1
    DOMAIN_WEIGHT = 0.3

    if not USE_LLM_RERANK:
        out = []
        for j in base_sorted[:RETURN_TOPK]:
            jj = clean_mongo(j.copy())
            sim = float(j.get("similarity") or 0.0)
            ov = float(j.get("_overlap_score") or 0.0)
            dom = float(j.get("_domain_score") or 0.0)
            final = SIM_WEIGHT * sim + OVERLAP_WEIGHT * ov + DOMAIN_WEIGHT * dom
            jj["similarity"] = sim
            jj["skill_overlap"] = ov
            jj["domain_score"] = dom
            jj["score"] = final
            jj["domains"] = list(j.get("_domains") or [])
            out.append(jj)
        return out

    rerank_pool = base_sorted[: min(len(base_sorted), 40)]
    candidate_obj = normalize_candidate(candidate_dict)
    ranking = match_candidate_to_jobs(candidate_obj, rerank_pool)

    idx_to_llm = {}
    for r in ranking:
        try:
            idx = int(r.get("job_index", 0)) - 1
            sc = float(r.get("score"))
            if 0 <= idx < len(rerank_pool):
                idx_to_llm[idx] = sc
        except Exception:
            continue

    scored = []
    for i, j in enumerate(rerank_pool):
        jj = clean_mongo(j.copy())
        sim = float(j.get("similarity") or 0.0)
        ov = float(j.get("_overlap_score") or 0.0)
        dom = float(j.get("_domain_score") or 0.0)
        llm_score = idx_to_llm.get(i, None)

        base_score = float(llm_score) if llm_score is not None else sim
        final = (SIM_WEIGHT * base_score) + (OVERLAP_WEIGHT * ov) + (DOMAIN_WEIGHT * dom)

        jj["similarity"] = sim
        jj["skill_overlap"] = ov
        jj["domain_score"] = dom
        jj["llm_score"] = llm_score
        jj["score"] = final
        jj["domains"] = list(j.get("_domains") or [])
        scored.append(jj)

    scored.sort(
        key=lambda x: (
            float(x.get("score") or 0.0),
            str(x.get("url") or x.get("_id") or ""),
        ),
        reverse=True,
    )
    return scored[:RETURN_TOPK]


@app.post("/upload_cv")
async def upload_cv(
    file: UploadFile = File(...),
    full_name: str = Form(""),
):
    try:
        text = extract_text_from_pdf(file)
        cv = extract_cv_data(text)

        if full_name and full_name.strip() and full_name.strip().lower() not in ["enter your name", "enter your name "]:
            cv["full_name"] = full_name.strip()

        if not looks_like_cv(cv):
            return {
                "status": "ERROR",
                "detail": "Uploaded PDF does not look like a CV (not enough CV signal).",
                "candidate": clean_mongo(cv),
                "matches": [],
            }

        save_candidate(cv)

        emb_text = cv_to_text_for_embedding(cv)
        cv_emb = embed_text(emb_text)

        jobs = find_top_jobs_by_embedding(cv_emb, top_k=EMBED_TOPK)
        jobs = dedup_jobs_by_url(jobs)

        matches = _rank_jobs(cv, jobs)

        # ---------- NEW: global threshold for NON-IT / NON-DATA ----------
        best_score = 0.0
        for m in matches:
            raw = m.get("score") or m.get("match_score")
            try:
                s = float(raw)
            except Exception:
                continue
            if s > best_score:
                best_score = s

        if best_score < NON_IT_THRESHOLD:
            return {
                "status": "NON_IT",
                "detail": "Top matching score below threshold; profile likely outside IT/Data vs job base.",
                "threshold": NON_IT_THRESHOLD,
                "max_score": best_score,
                "candidate": clean_mongo(cv),
                "matches": [],
            }
        # ---------------------------------------------------------------

        return {
            "status": "OK",
            "candidate": clean_mongo(cv),
            "matches": matches,
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


@app.post("/jobs/ingest")
def ingest_job(job: JobOffer):
    job_dict = job.dict()
    emb_text = job_to_text_for_embedding(job_dict)
    job_dict["embedding"] = embed_text(emb_text)
    save_job(job_dict)
    return {"status": "OK", "inserted": True}


@app.get("/test_llm_direct")
def test_llm_direct():
    system_prompt = "You are a job-matching AI. Return JSON only."
    user_prompt = """
Candidate:
Skills = ["Python", "AWS", "Airflow"]
Experiences = ["Data Engineer 3 years"]

Jobs:
JOB 1:
Title: Python Data Engineer
Description: Looking for Python, ETL, Airflow, AWS.

Return ONLY JSON:
[
  {"job_index": 1, "score": 0.90}
]
"""
    result = call_openrouter(
        # model="qwen/qwen-2.5-7b-instruct",
        model="qwen/qwen3-coder:free",
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
