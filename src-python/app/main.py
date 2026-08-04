from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.ma_router import router as ma_router

app = FastAPI(
    title="VaultAI Engine",
    description="Air-Gapped Offline M&A Risk Extraction & Compliance Engine"
)

# Enable CORS for local Tauri development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register M&A Router
app.include_router(ma_router)

@app.get("/health")
def health_check():
    return {"status": "online", "mode": "air-gapped", "engine": "M&A Risk Extractor"}