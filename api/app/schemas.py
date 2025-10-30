from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal

class Location(BaseModel):
    city: Optional[str] = None
    country: Optional[str] = None
    remote: Optional[Literal["no","hybrid","full"]] = None

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
    email: Optional[EmailStr] = None
    location: Optional[Location] = None
    skills_declared: List[str] = Field(default_factory=list)
    experiences: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    profile_source: str = "form|cv"

class JobPostingIn(BaseModel):
    source: str
    url: Optional[str] = None
    title: str
    company: Optional[str] = None
    location: Optional[Location] = None
    contract_type: Optional[str] = None
    seniority: Optional[str] = None
    skills_required: List[str] = Field(default_factory=list)
    skills_nice: List[str] = Field(default_factory=list)
    description_text: Optional[str] = None
    collected_at: Optional[str] = None
