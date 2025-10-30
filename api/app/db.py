import os
from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "matcher")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

def ensure_indexes():
    db.job_postings.create_index([("title", "text"), ("description_text", "text"), ("skills_required", "text")], name="jobs_text_idx", default_language="french")
    db.candidates.create_index([("full_name", 1)])
    db.candidates.create_index([("skills_declared", "text")], name="cand_skills_text", default_language="french")
    db.matches.create_index([("job_ref", 1), ("score",-1)])
