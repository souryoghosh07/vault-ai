import os
import sys

# Tell the Hugging Face hub to operate completely offline
os.environ["HF_HUB_OFFLINE"] = "1"

# If running as a compiled PyInstaller executable, reroute the cache to the internal temp folder
if getattr(sys, 'frozen', False):
    os.environ["HF_HOME"] = os.path.join(sys._MEIPASS, "hf_cache")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.soc_router import router as soc_router

app = FastAPI(
    title="Vault AI SOC Engine",
    description="Air-Gapped Tier-1 SOC Incident Triage & Forensic Log Analysis",
    version="1.0.0",
)

# Enable CORS for local Tauri development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register SOC Incident Triage Router
app.include_router(soc_router)


@app.get("/health")
def health_check():
    return {
        "status": "online",
        "mode": "air-gapped",
        "engine": "Tier-1 SOC Incident Triage",
        "primary_threat": "Cisco ISE Auth Bypass (CVE-2026-76460)",
    }