from pydantic import BaseModel, Field
from typing import List, Optional


# ===============================
#   CV EXTRACTED DATA SCHEMA
# ===============================

class CVExperience(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    years: Optional[str] = None


class CVLanguage(BaseModel):
    name: Optional[str] = None
    level: Optional[str] = None


class CVEducation(BaseModel):
    degree: Optional[str] = None
    school: Optional[str] = None
    year: Optional[str] = None


class CandidateCV(BaseModel):
    full_name: str
    summary: Optional[str]
    skills_detected: List[str] = []
    languages: List[CVLanguage] = []
    experiences: List[CVExperience] = []
    education: List[CVEducation] = []
# ===============================
#      JOB OFFER SCHEMA
# ===============================

class JobOffer(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    url: Optional[str] = None
    description_text: Optional[str] = None
    location: Optional[dict] = None
    contract_type: Optional[str] = None
    skills_required: List[str] = []
    skills_nice: List[str] = []
    seniority: Optional[str] = None
    source: Optional[str] = None
