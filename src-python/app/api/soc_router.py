import traceback
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.services.soc_service import process_security_incident

router = APIRouter()

SUPPORTED_EXTENSIONS = (
    ".evtx",
    ".pcap",
    ".pcapng",
    ".cap",
    ".log",
    ".txt",
    ".json",
    ".csv",
    ".xml",
    ".syslog",
    ".pdf",
)


class SOCReport(BaseModel):
    filename: str
    threat_profile: str
    report_markdown: str


class ThreatProfileInfo(BaseModel):
    id: str
    name: str
    description: str
    signatures: List[str]


@router.get("/api/soc/profiles", response_model=List[ThreatProfileInfo])
async def list_threat_profiles():
    """Returns available high-severity threat detection profiles."""
    return [
        ThreatProfileInfo(
            id="cisco_ise",
            name="Cisco ISE Auth Bypass (CVE-2026-76460)",
            description="Detects unauthenticated REST API abuse against Cisco ISE / Kong gateway leading to root execution.",
            signatures=[
                "Unauthenticated API hits (/api/v1/..., /ise/..., /admin/...)",
                "Kong Gateway access anomalies (ise-kong/access.log)",
                "Root process spawning (bash, sh, sudo) following API calls",
                "Anomalous session tokens or missing Authorization headers",
                "Anomalous external C2 egress from appliance",
            ],
        ),
        ThreatProfileInfo(
            id="cobalt_strike",
            name="Cobalt Strike Beaconing & C2",
            description="Identifies periodic command-and-control beaconing, process injection, and named pipes.",
            signatures=[
                "Periodic HTTP/DNS requests with jitter",
                "Process injection into trusted binaries (rundll32, powershell)",
                "Named pipe IPC communication",
                "Staged shellcode memory allocations",
            ],
        ),
        ThreatProfileInfo(
            id="log4shell",
            name="Log4Shell & Web RCE (CVE-2021-44228)",
            description="Detects JNDI injection attempts and webshell drops across web logs.",
            signatures=[
                "${jndi:ldap://...} and ${jndi:rmi://...} patterns",
                "Outbound LDAP / RMI connections from server",
                "ProxyLogon /ecp/ requests with X-BEResource cookies",
                "Dropped webshells in web-accessible directories",
            ],
        ),
        ThreatProfileInfo(
            id="general_triage",
            name="Universal SOC Log Triage",
            description="Performs broad anomaly detection across EVTX, PCAP, and syslog streams.",
            signatures=[
                "Brute force and failed logon bursts (Event 4625)",
                "Privilege escalation and new service creations (Event 7045)",
                "Unusual port scanning or lateral network connections",
                "Suspicious script execution (cmd.exe, powershell.exe -enc)",
            ],
        ),
    ]


@router.post("/api/soc/analyze", response_model=SOCReport)
async def analyze_security_artifact(
    file: UploadFile = File(...),
    threat_profile: str = Form("cisco_ise"),
    model_name: Optional[str] = Form(None),
):
    """Ingests a security artifact (.evtx, .pcap, .log, .pdf, etc.) and performs deterministic Tier-1 SOC triage."""
    filename = file.filename or "unknown_artifact"
    lower_name = filename.lower()

    if not any(lower_name.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported artifact format. Supported extensions: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    try:
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        report_markdown = await process_security_incident(
            file_bytes=contents,
            filename=filename,
            threat_profile=threat_profile,
            model_name=model_name,
        )

        return SOCReport(
            filename=filename,
            threat_profile=threat_profile,
            report_markdown=report_markdown,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Tier-1 SOC Analysis failed: {str(e)}")
