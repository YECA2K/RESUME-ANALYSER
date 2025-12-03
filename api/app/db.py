# api/app/db.py
from pymongo import MongoClient
import os
from datetime import datetime
from typing import List, Dict, Any
import numpy as np
from bson import ObjectId


MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
DB_NAME = os.getenv("DB_NAME", "matcher")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]


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
    job["ingested_at"] = datetime.utcnow()
    db.jobs.insert_one(job)


def load_jobs(limit=50):
    docs = list(db.jobs.find().limit(limit))
    return clean_mongo(docs)


def load_jobs_with_embeddings(max_jobs=2000):
    docs = list(
        db.jobs.find(
            {"embedding": {"$exists": True}},
            limit=max_jobs,
        )
    )
    return clean_mongo(docs)


# -------------------------------------------------------------------
# SIMILARITY SEARCH
# -------------------------------------------------------------------
def find_top_jobs_by_embedding(query_emb, top_k=50, max_jobs=2000):
    """
    Retourne les jobs les plus proches du CV sur la base des embeddings.
    Ajoute un champ 'similarity' dans chaque job.
    - query_emb : embedding du CV (list/np.array)
    - top_k : nombre de jobs à renvoyer
    - max_jobs : nombre max de jobs à charger pour le calcul
    """
    if query_emb is None:
        return []

    # 1) Récupérer les jobs qui ont un embedding
    jobs = list(
        db.jobs.find(
            {"embedding": {"$exists": True}},
            limit=max_jobs,
        )
    )

    if not jobs:
        return []

    # 2) Construire la matrice des embeddings
    valid_jobs = []
    matrix = []

    for job in jobs:
        emb = job.get("embedding")
        if isinstance(emb, list) and len(emb) > 0:
            valid_jobs.append(job)
            matrix.append(emb)

    if not matrix:
        return []

    M = np.asarray(matrix, dtype=float)  # shape (N, D)
    q = np.asarray(query_emb, dtype=float)  # shape (D,)

    # Sécuriser la forme
    if q.ndim != 1:
        q = q.flatten()

    # 3) Normalisation pour cosine similarity
    M_norm = np.linalg.norm(M, axis=1, keepdims=True) + 1e-8
    q_norm = np.linalg.norm(q) + 1e-8

    M_unit = M / M_norm
    q_unit = q / q_norm

    # sims[i] = cos(M[i], q)
    sims = np.dot(M_unit, q_unit)  # shape (N,)

    # 4) Prendre les top_k meilleurs
    top_k = min(int(top_k), len(valid_jobs))
    indices = np.argsort(-sims)[:top_k]  # ordre décroissant

    results = []
    for idx in indices:
        j = valid_jobs[int(idx)].copy()
        j["similarity"] = float(sims[int(idx)])  # score du matching embedding
        results.append(j)

    return results
