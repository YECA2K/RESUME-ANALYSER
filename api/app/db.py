# api/app/db.py
from pymongo import MongoClient, ASCENDING
import os
from datetime import datetime
import numpy as np
from bson import ObjectId

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
DB_NAME = os.getenv("DB_NAME", "matcher")

# How many jobs max we load in RAM to compute similarity (cosine)
# With 9k jobs, you can safely set 20000
DEFAULT_MAX_JOBS = int(os.getenv("MATCH_MAX_JOBS", "20000"))

client = MongoClient(MONGO_URL)
db = client[DB_NAME]


# -------------------------------------------------------------------
# INIT (indexes)
# -------------------------------------------------------------------
def ensure_indexes():
    """
    Creates helpful indexes once. Safe to call multiple times.
    - url unique sparse: prevents duplicating same job daily
    """
    try:
        db.jobs.create_index([("url", ASCENDING)], unique=True, sparse=True)
    except Exception:
        # If duplicates already exist, Mongo may refuse unique index creation.
        # You can dedupe manually in Mongo then retry.
        pass

    try:
        db.candidates.create_index([("created_at", ASCENDING)])
    except Exception:
        pass


ensure_indexes()


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------
def clean_mongo(doc):
    """
    Convert MongoDB ObjectId -> str so FastAPI can return JSON safely.
    Works recursively on nested dicts + lists.
    """
    if isinstance(doc, list):
        return [clean_mongo(x) for x in doc]

    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                out[k] = str(v)
            else:
                out[k] = clean_mongo(v)
        return out

    return doc


# -------------------------------------------------------------------
# CANDIDATE STORAGE
# -------------------------------------------------------------------
def save_candidate(cv_data: dict):
    cv_data["created_at"] = datetime.utcnow()
    r = db.candidates.insert_one(cv_data)
    return str(r.inserted_id)


def load_last_candidate():
    doc = db.candidates.find_one(sort=[("created_at", -1)])
    return clean_mongo(doc) if doc else None


# -------------------------------------------------------------------
# JOB STORAGE
# -------------------------------------------------------------------
def save_job(job: dict):
    """
    UPSERT job to avoid duplicates across daily scraping.
    Prefer URL as unique key, else fallback to (title,company,source).
    """
    job["ingested_at"] = datetime.utcnow()

    url = (job.get("url") or "").strip()
    if url:
        key = {"url": url}
    else:
        key = {
            "title": (job.get("title") or "").strip(),
            "company": (job.get("company") or "").strip(),
            "source": (job.get("source") or "").strip(),
        }

    db.jobs.update_one(key, {"$set": job}, upsert=True)


def load_jobs(limit=50):
    docs = list(db.jobs.find().limit(limit))
    return clean_mongo(docs)


def load_jobs_with_embeddings(max_jobs=2000):
    docs = list(
        db.jobs.find({"embedding": {"$exists": True}}, limit=max_jobs)
    )
    return clean_mongo(docs)


# -------------------------------------------------------------------
# SIMILARITY SEARCH
# -------------------------------------------------------------------
def find_top_jobs_by_embedding(query_emb, top_k=50, max_jobs=None):
    """
    Returns top_k jobs closest to CV embedding (cosine similarity).
    Adds 'similarity' float field to each job.

    - query_emb: list/np.array
    - top_k: number to return
    - max_jobs: max jobs loaded to compute similarity (default env MATCH_MAX_JOBS)
    """
    if query_emb is None:
        return []

    if max_jobs is None:
        max_jobs = DEFAULT_MAX_JOBS

    # Pull jobs with embeddings
    jobs = list(
        db.jobs.find({"embedding": {"$exists": True}}, limit=int(max_jobs))
    )
    if not jobs:
        return []

    valid_jobs = []
    matrix = []

    for job in jobs:
        emb = job.get("embedding")
        if isinstance(emb, list) and len(emb) > 0:
            valid_jobs.append(job)
            matrix.append(emb)

    if not matrix:
        return []

    M = np.asarray(matrix, dtype=float)        # (N, D)
    q = np.asarray(query_emb, dtype=float)     # (D,)

    if q.ndim != 1:
        q = q.flatten()

    # cosine similarity
    M_norm = np.linalg.norm(M, axis=1, keepdims=True) + 1e-8
    q_norm = np.linalg.norm(q) + 1e-8
    M_unit = M / M_norm
    q_unit = q / q_norm

    sims = np.dot(M_unit, q_unit)  # (N,)

    top_k = min(int(top_k), len(valid_jobs))
    indices = np.argsort(-sims)[:top_k]

    results = []
    for idx in indices:
        j = valid_jobs[int(idx)].copy()
        j["similarity"] = float(sims[int(idx)])
        results.append(j)

    return results
