# api/app/schemas.py
from typing import Optional, List
from pydantic import BaseModel, field_validator

class Location(BaseModel):
    city: Optional[str] = None
    country: Optional[str] = None
    remote: Optional[str] = None   # "full" | "hybrid" | "no"

    @field_validator("*", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v


class JobPostingIn(BaseModel):
    source: str = "jobspy"
    url: Optional[str] = None
    title: str
    company: Optional[str] = None
    location: Location = Location()
    contract_type: Optional[str] = None
    seniority: Optional[str] = None
    skills_required: List[str] = []
    skills_nice: List[str] = []
    description_text: str = ""
    collected_at: Optional[str] = None

    # --------- Nettoyage prévention NaN / floats invalides ----------
    @field_validator(
        "title", "company", "contract_type", "seniority",
        "description_text", mode="before")
    @classmethod
    def sanitize_str(cls, v):
        import math
        if v is None:
            return None
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return str(v).strip() or None

    @field_validator("skills_required", "skills_nice", mode="before")
    @classmethod
    def sanitize_list(cls, v):
        if not v:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []


# ===== CANDIDATES ======

class Experience(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    years: Optional[float] = None

class Education(BaseModel):
    degree: Optional[str] = None
    school: Optional[str] = None
    year: Optional[int] = None

class CandidateIn(BaseModel):
    full_name: str
    email: Optional[str] = None
    location: Optional[Location] = None
    skills_declared: List[str] = []
    experiences: List[Experience] = []
    education: List[Education] = []
    languages: List[str] = []
    profile_source: str = "form|cv"
