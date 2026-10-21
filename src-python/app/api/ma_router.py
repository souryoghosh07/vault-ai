import traceback
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.services.ma_service import process_document
from app.prompts.ma_prompts import MA_SYSTEM_PROMPT, MA_SYNTHESIS_RULES, DEFAULT_CLEAN_REPORT
from app.prompts.pitch_prompts import PITCH_DECK_SYSTEM_PROMPT, PITCH_SYNTHESIS_RULES, DEFAULT_PITCH_REPORT

router = APIRouter()

class AuditReport(BaseModel):
    filename: str
    report_markdown: str

MARedFlagReport = AuditReport
PitchDeckReport = AuditReport

async def _run_audit(file: UploadFile, system_prompt: str, synthesis_rules: str, default_report: str, label: str) -> AuditReport:
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported.")
    try:
        contents = await file.read()
        report_markdown = await process_document(
            file_bytes=contents,
            filename=file.filename,
            system_prompt=system_prompt,
            synthesis_rules=synthesis_rules,
            default_report=default_report
        )
        return AuditReport(filename=file.filename, report_markdown=report_markdown)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{label} Audit failed: {e}")

@router.post("/api/ma/parse", response_model=AuditReport)
async def parse_legal_document(file: UploadFile = File(...)):
    return await _run_audit(file, MA_SYSTEM_PROMPT, MA_SYNTHESIS_RULES, DEFAULT_CLEAN_REPORT, "Legal")

@router.post("/api/pitch/parse", response_model=AuditReport)
async def parse_pitch_deck(file: UploadFile = File(...)):
    return await _run_audit(file, PITCH_DECK_SYSTEM_PROMPT, PITCH_SYNTHESIS_RULES, DEFAULT_PITCH_REPORT, "Pitch Deck")