import os
import json
import fitz  # PyMuPDF
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
# TEST OPENROUTER (simple)
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
    Lit le PDF en mémoire et renvoie le texte brut.
    """
    try:
        pdf = fitz.open(stream=file.file.read(), filetype="pdf")
        text = "".join(page.get_text() for page in pdf)
        pdf.close()
        return text
    except Exception as e:
        raise Exception(f"PDF extraction failed: {e}")


# ======================================================
# TEXT BUILDERS POUR EMBEDDINGS
# ======================================================
def cv_to_text_for_embedding(cv: dict) -> str:
    """
    Construit un texte compact (summary + skills + expériences) pour l'embedding.
    """
    parts = []

    if cv.get("summary"):
        parts.append(cv["summary"])

    skills = cv.get("skills") or []
    if skills:
        parts.append("Skills: " + ", ".join(skills))

    for exp in cv.get("experiences", []):
        if isinstance(exp, dict):
            seg = " ".join(
                [
                    exp.get("title", "") or exp.get("position", ""),
                    exp.get("company", ""),
                    exp.get("period", "") or exp.get("years", ""),
                    exp.get("summary", "")[:200],
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
    """
    Construit un texte de job pour l'embedding.
    """
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
# NORMALISATION CANDIDAT POUR LLM
# ======================================================
def normalize_candidate(d: dict):
    """
    Convertit un dict Mongo en petit objet avec les bons attributs
    pour le LLM (full_name, summary, skills, experiences).
    """

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


# ======================================================
# TEST CV EXTRACTION
# ======================================================
@app.post("/test_extract")
async def test_extract(file: UploadFile = File(...)):
    try:
        text = extract_text_from_pdf(file)
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
    """
    Teste le pipeline de matching sur le dernier candidat en DB.
    Renvoie déjà les jobs complets + score.
    """
    cand = load_last_candidate()
    if not cand:
        return {"status": "ERROR", "detail": "No candidate in DB"}

    # 1) Embedding du candidat
    emb_text = cv_to_text_for_embedding(cand)
    cv_emb = embed_text(emb_text)

    # 2) Recherche des jobs proches par embeddings
    jobs = find_top_jobs_by_embedding(cv_emb, top_k=30)
    if not jobs:
        jobs = load_jobs(limit=30)

    # 3) Re-ranking via LLM
    candidate_obj = normalize_candidate(cand)
    ranking = match_candidate_to_jobs(candidate_obj, jobs)

    full_matches = []

    # Remap job_index -> job réel
    for r in ranking:
        try:
            idx = int(r.get("job_index", 0)) - 1  # LLM renvoie 1-based
            if 0 <= idx < len(jobs):
                job = jobs[idx].copy()
                job = clean_mongo(job)
                job["score"] = r.get("score")
                full_matches.append(job)
        except Exception:
            continue

    # Fallback : si aucun match exploitable, renvoyer 20 premiers jobs
    # en utilisant la similarité embedding comme score
    if not full_matches and jobs:
        for job in jobs[:20]:
            j = clean_mongo(job)
            sim = job.get("similarity")
            try:
                j["score"] = float(sim) if sim is not None else 0.0
            except Exception:
                j["score"] = 0.0
            full_matches.append(j)

    # Tri par score décroissant si possible
    def sort_key(j):
        s = j.get("score")
        try:
            return float(s) if s is not None else 0.0
        except Exception:
            return 0.0

    full_matches = sorted(full_matches, key=sort_key, reverse=True)

    return {
        "status": "OK",
        "candidate": clean_mongo(cand),
        "matches": full_matches,
    }


# ======================================================
# FULL WORKFLOW — UPLOAD CV
# ======================================================
@app.post("/upload_cv")
async def upload_cv(
    file: UploadFile = File(...),
    full_name: str = Form(""),
):
    """
    1) PDF -> texte
    2) Extraction structurée via LLM
    3) Sauvegarde en DB
    4) Embedding + recherche des jobs proches
    5) Re-ranking via LLM
    6) Retourne les jobs complets (titre, company, url, description_text, score)
    """
    try:
        # 1) PDF -> texte
        text = extract_text_from_pdf(file)

        # 2) Extraction LLM
        cv = extract_cv_data(text)

        if full_name:
            cv["full_name"] = full_name

        # 3) Sauvegarde candidat
        save_candidate(cv)

        # 4) Embedding + recherche de jobs
        emb_text = cv_to_text_for_embedding(cv)
        cv_emb = embed_text(emb_text)

        jobs = find_top_jobs_by_embedding(cv_emb, top_k=50)
        if not jobs:
            jobs = load_jobs(limit=50)

        # 5) Re-ranking LLM
        candidate_obj = normalize_candidate(cv)
        ranking = match_candidate_to_jobs(candidate_obj, jobs)

        full_matches = []

        for r in ranking:
            try:
                idx = int(r.get("job_index", 0)) - 1  # 1-based -> 0-based
                if 0 <= idx < len(jobs):
                    job = jobs[idx].copy()
                    job = clean_mongo(job)
                    job["score"] = r.get("score")
                    full_matches.append(job)
            except Exception:
                continue

        # Nettoyage des scores en float si possible
        cleaned = []
        for j in full_matches:
            s = j.get("score")
            try:
                if s is None:
                    cleaned.append(j)
                else:
                    j["score"] = float(s)
                    cleaned.append(j)
            except Exception:
                continue
        full_matches = cleaned

        # 6) Fallback si aucune match LLM : renvoyer un minimum de jobs
        # en utilisant la similarité embedding comme score
        if not full_matches and jobs:
            for job in jobs[:20]:
                j = clean_mongo(job)
                sim = job.get("similarity")
                try:
                    j["score"] = float(sim) if sim is not None else 0.0
                except Exception:
                    j["score"] = 0.0
                full_matches.append(j)

        # Tri par score décroissant
        def sort_key(j):
            s = j.get("score")
            try:
                return float(s) if s is not None else 0.0
            except Exception:
                return 0.0

        full_matches = sorted(full_matches, key=sort_key, reverse=True)

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
# INGESTION D'UNE OFFRE (utilisé par le script normalize)
# ======================================================
@app.post("/jobs/ingest")
def ingest_job(job: JobOffer):
    job_dict = job.dict()

    emb_text = job_to_text_for_embedding(job_dict)
    job_dict["embedding"] = embed_text(emb_text)

    save_job(job_dict)
    return {"status": "OK", "inserted": True}


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
