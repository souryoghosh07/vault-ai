from pydantic import BaseModel
from typing import List, Optional

class RiskFinding(BaseModel):
    category: str  # e.g., "Change of Control", "Customer Concentration"
    finding: str
    risk_level: Optional[str] = "Unspecified" # High, Moderate, Low, None
    citation: str  # e.g., "Section 8.4, Page 22" or "Not found in document"

class MARedFlagReport(BaseModel):
    filename: str
    report_markdown: str
    findings: Optional[List[RiskFinding]] = []

class PitchDeckReport(BaseModel):
    filename: str
    report_markdown: str    