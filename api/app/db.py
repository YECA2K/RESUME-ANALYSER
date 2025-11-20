from pymongo import MongoClient
import os
from datetime import datetime

# MongoDB connection
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
DB_NAME = os.getenv("DB_NAME", "matcher")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]


# -------------------------------
# CANDIDATE CV STORAGE
# -------------------------------

def save_candidate(cv_data: dict):
    """Save extracted CV in MongoDB."""
    cv_data["created_at"] = datetime.utcnow()
    result = db.candidates.insert_one(cv_data)
    return str(result.inserted_id)


def load_last_candidate():
    """Load the most recently saved CV."""
    return db.candidates.find_one(sort=[("created_at", -1)])


# -------------------------------
# JOB OFFERS STORAGE
# -------------------------------

def save_job(job: dict):
    job["ingested_at"] = datetime.utcnow()
    db.jobs.insert_one(job)


def load_jobs(limit=50):
    """Load job offers (limit to avoid LLM overload)."""
    return list(db.jobs.find().limit(limit))
