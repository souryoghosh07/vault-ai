from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.services.ma_service import process_document

# Import Legal variables from ma_prompts
from app.prompts.ma_prompts import (
    MA_SYSTEM_PROMPT, MA_SYNTHESIS_RULES, DEFAULT_CLEAN_REPORT
)

# Import Pitch Deck variables from the new pitch_prompts file
from app.prompts.pitch_prompts import (
    PITCH_DECK_SYSTEM_PROMPT, PITCH_SYNTHESIS_RULES, DEFAULT_PITCH_REPORT
)

import traceback

router = APIRouter()

# --- Schemas ---
class MARedFlagReport(BaseModel):
    filename: str
    report_markdown: str

class PitchDeckReport(BaseModel):
    filename: str
    report_markdown: str

# --- Legal M&A Endpoint ---
@router.post("/api/ma/parse", response_model=MARedFlagReport)
async def parse_legal_document(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported.")

    try:
        contents = await file.read()
        report_markdown = await process_document(
            file_bytes=contents,
            filename=file.filename,
            system_prompt=MA_SYSTEM_PROMPT,
            synthesis_rules=MA_SYNTHESIS_RULES,
            default_report=DEFAULT_CLEAN_REPORT
        )
        return MARedFlagReport(filename=file.filename, report_markdown=report_markdown)
    except Exception as e:
        print("\n--- [FATAL ERROR] ---")
        traceback.print_exc()
        print("---------------------\n")
        raise HTTPException(status_code=500, detail=f"Legal Audit failed: {str(e)}")

# --- Pitch Deck Endpoint ---
@router.post("/api/pitch/parse", response_model=PitchDeckReport)
async def parse_pitch_deck(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported.")

    try:
        contents = await file.read()
        report_markdown = await process_document(
            file_bytes=contents,
            filename=file.filename,
            system_prompt=PITCH_DECK_SYSTEM_PROMPT,
            synthesis_rules=PITCH_SYNTHESIS_RULES,
            default_report=DEFAULT_PITCH_REPORT
        )
        return PitchDeckReport(filename=file.filename, report_markdown=report_markdown)
    except Exception as e:
        print("\n--- [FATAL ERROR] ---")
        traceback.print_exc()
        print("---------------------\n")
        raise HTTPException(status_code=500, detail=f"Pitch Deck Audit failed: {str(e)}")