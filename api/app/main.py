import os
import json
import fitz
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

from app.db import save_candidate, load_last_candidate, load_jobs
from app.llm.extract_cv_openrouter import extract_cv_data
from app.llm.matcher_openrouter import match_candidate_to_jobs
from app.llm.openrouter_client import call_openrouter

app = FastAPI(title="Resume Matcher API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# Health
# ============================
@app.get("/health")
def health():
    return {"status": "OK"}

# ============================
# TEST OPENROUTER
# ============================
@app.get("/test_openrouter")
def test_openrouter():
    try:
        resp = call_openrouter(
            model="qwen/qwen-2.5-7b-instruct",
            messages=[{"role": "user", "content": "Say YES"}],
            max_tokens=10,
        )
        return {"status": "OK", "response": resp}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}

# ============================
# PDF extraction
# ============================
def extract_text_from_pdf(file: UploadFile):
    try:
        pdf = fitz.open(stream=file.file.read(), filetype="pdf")
        text = ""
        for page in pdf:
            text += page.get_text()
        pdf.close()
        return text
    except Exception as e:
        raise Exception(f"PDF extraction failed: {e}")

# ============================
# TEST EXTRACT
# ============================
@app.post("/test_extract")
async def test_extract(file: UploadFile = File(...)):
    try:
        text = extract_text_from_pdf(file)
        result = extract_cv_data(text)
        return result
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}

# ============================
# FIX: Normalisation candidate object
# ============================
def normalize_candidate(candidate_dict):

    class CandidateObj:
        pass

    c = CandidateObj()

    # copy dict → object
    for k, v in candidate_dict.items():
        setattr(c, k, v)

    # 🔥 FIX PRINCIPAL
    if hasattr(c, "skills_detected"):
        pass
    elif hasattr(c, "skills"):
        c.skills_detected = c.skills
    else:
        c.skills_detected = []

    # 🔥 rendre robuste
    if not hasattr(c, "experiences"):
        c.experiences = []

    if not hasattr(c, "summary"):
        c.summary = ""

    if not hasattr(c, "full_name"):
        c.full_name = ""

    return c

# ============================
# TEST MATCHING
# ============================
@app.get("/test_matching")
def test_matching():

    jobs = load_jobs(limit=20)
    if not jobs:
        return {"status": "ERROR", "detail": "No jobs in DB"}

    candidate_dict = load_last_candidate()
    if not candidate_dict:
        return {"status": "ERROR", "detail": "No candidate in DB"}

    # 🔥 FIX: always normalize
    candidate = normalize_candidate(candidate_dict)

    try:
        matches = match_candidate_to_jobs(candidate, jobs)
        return {"status": "OK", "matches": matches}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}

# ============================
# WORKFLOW COMPLET
# ============================
@app.post("/upload_cv")
async def upload_cv(
    file: UploadFile = File(...),
    full_name: str = Form(...)
):
    try:
        text = extract_text_from_pdf(file)
        cv_data = extract_cv_data(text)
        cv_data["full_name"] = full_name

        save_candidate(cv_data)

        jobs = load_jobs(limit=50)

        candidate = normalize_candidate(cv_data)

        matches = match_candidate_to_jobs(candidate, jobs)

        return {"candidate": cv_data, "matches": matches}

    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}
