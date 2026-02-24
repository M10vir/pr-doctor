from pydantic import BaseModel, Field
from typing import List, Literal, Optional

Severity = Literal["low", "medium", "high", "critical"]
Category = Literal["bug_risk", "security", "quality", "tests", "docs"]

class Finding(BaseModel):
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    file: Optional[str] = None
    line_hint: Optional[str] = None
    title: str
    recommendation: str

class ReviewResult(BaseModel):
    summary: str
    overall_risk: Severity
    findings: List[Finding] = []
