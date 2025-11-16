import os
import fitz  # pymupdf
import numpy as np
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

from llm.extract_cv_openrouter import extract_cv_data
from llm.embeddings import embed_text
from llm.matcher_openrouter import score_candidate_against_job

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "matcher")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]
candidates = db.candidates
jobs = db.jobs


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload_cv")
async def upload_cv(file: UploadFile, full_name: str = Form(...)):
    # ---- PDF extraction ----
    try:
        pdf = fitz.open(stream=await file.read(), filetype="pdf")
        text = ""
        for page in pdf:
            text += page.get_text()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF extraction failed: {e}")

    # ---- LLM #1 extraction ----
    llm_data = extract_cv_data(text)
    llm_data["full_name"] = full_name

    # ---- Compute CV vector ----
    cv_vector = embed_text(text)
    llm_data["vector"] = cv_vector

    inserted = candidates.insert_one(llm_data)

    return {"candidate_id": str(inserted.inserted_id), **llm_data}


@app.get("/match/{candidate_id}")
def match_candidate(candidate_id: str):
    cv = candidates.find_one({"_id": candidate_id})
    if not cv:
        raise HTTPException(404, "Candidate not found")

    cv_vector = cv["vector"]

    # ---- VECTOR SEARCH top 10 ----
    scored = []
    for job in jobs.find():
        if "vector" not in job:
            continue

        sim = cosine_similarity(cv_vector, job["vector"])
        scored.append((sim, job))

    top10 = sorted(scored, key=lambda x: x[0], reverse=True)[:10]

    # ---- LLM #2 reranking ----
    results = []
    for sim, job in top10:
        llm_score = score_candidate_against_job(cv, job)
        results.append({
            "job": job,
            "similarity": sim,
            "score": llm_score.get("score", 0),
            "reason": llm_score.get("reason", "")
        })

    # Return top 5 ranked by score
    final = sorted(results, key=lambda x: x["score"], reverse=True)[:5]

    return {"results": final}
