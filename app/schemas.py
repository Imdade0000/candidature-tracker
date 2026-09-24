"""Modèles de données échangés par l'API."""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Application(BaseModel):
    id: str
    company: str
    title: str
    stack: List[str] = Field(default_factory=list)
    location: str = ""
    remote: str = ""
    seniority_required: str = ""
    status: str = ""
    date: str = ""
    notes: str = ""


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    sources: List[str]  # ids des candidatures utilisées comme contexte


class ScoreJobRequest(BaseModel):
    title: str
    description: str


class ScoreJobResponse(BaseModel):
    score: int  # 0-100
    matched_skills: List[str]
    missing_skills: List[str]
    flags: List[str]
    recommendation: str
    explanation: str


class MonthBreakdown(BaseModel):
    total: int = 0
    remote: int = 0
    hybrid: int = 0
    onsite: int = 0


class StatsResponse(BaseModel):
    total: int
    by_month: Dict[str, MonthBreakdown]
    by_status: Dict[str, int]
    by_remote: Dict[str, int]
    by_seniority: Dict[str, int]


class Alert(BaseModel):
    id: str
    score: int
    title: str
    company: str = ""
    url: str = ""
    source: str = ""
    category: str = ""
    published: str = ""
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    recommendation: str = ""
    explanation: str = ""
    status: str = "new"
    created: str = ""


class ApplyAlertRequest(BaseModel):
    notes: str = ""


class Opportunity(BaseModel):
    id: str
    source: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    job_type: str = ""
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    url: str = ""
    published_at: str = ""
    score: int = 0
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    recommendation: str = ""
    status: str = "new"
    discovered_at: str = ""
    age_days: Optional[int] = None


class OpportunitiesRefreshResponse(BaseModel):
    fetched: int = 0
    above_threshold: int = 0
    added: int = 0
    expired: int = 0
    filtered: int = 0


class OpportunityStatusRequest(BaseModel):
    status: str


class DraftResponse(BaseModel):
    subject: str
    body: str