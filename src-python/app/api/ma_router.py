from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.ma_service import process_ma_document
from app.schemas.ma_schemas import MARedFlagReport

router = APIRouter(prefix="/api/ma", tags=["M&A Legal Engine"])

@router.post("/parse", response_model=MARedFlagReport)
async def parse_document(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported for M&A analysis.")

    try:
        contents = await file.read()
        report_markdown = await process_ma_document(contents, file.filename)
        return MARedFlagReport(filename=file.filename, report_markdown=report_markdown)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")