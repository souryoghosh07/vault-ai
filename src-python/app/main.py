import os
import sys

# Tell the Hugging Face hub to operate completely offline
os.environ["HF_HUB_OFFLINE"] = "1"

# If running as a compiled PyInstaller executable, reroute the cache to the internal temp folder
if getattr(sys, 'frozen', False):
    os.environ["HF_HOME"] = os.path.join(sys._MEIPASS, "hf_cache")

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