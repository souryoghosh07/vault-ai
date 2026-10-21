import io
import httpx
from typing import List
from app.parsers.artifact_parser import parse_security_artifact
from app.prompts.soc_prompts import (
    SOC_SYSTEM_PROMPT,
    SOC_SYNTHESIS_RULES,
    DEFAULT_CLEAN_SOC_REPORT,
)

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
EVENT_CHUNK_SIZE = 50
EVENT_OVERLAP = 5


def chunk_events(events: List[str], chunk_size: int = EVENT_CHUNK_SIZE, overlap: int = EVENT_OVERLAP) -> List[str]:
    """Chunks normalized event lines into bounded batches for local LLM inference."""
    if not events:
        return []

    chunks = []
    step = max(1, chunk_size - overlap)
    total_events = len(events)

    for i in range(0, total_events, step):
        batch = events[i : i + chunk_size]
        batch_text = "\n".join(batch)
        chunk_header = f"--- [LOG EVENT BATCH: Records {i + 1} to {min(i + len(batch), total_events)} of {total_events}] ---\n"
        chunks.append(chunk_header + batch_text)

        if i + chunk_size >= total_events:
            break

    return chunks


async def analyze_soc_chunk(
    client: httpx.AsyncClient,
    chunk_text: str,
    filename: str,
    model_name: str,
    system_prompt: str,
    threat_profile_hint: str = "Cisco ISE Auth Bypass (CVE-2026-76460) & High-Severity Threat Triage",
) -> str:
    """Executes deterministic Tier-1 SOC indicator extraction against an event chunk."""
    user_prompt = (
        f"FORENSIC ARTIFACT FILENAME: {filename}\n"
        f"TARGET PROFILE: {threat_profile_hint}\n\n"
        f"INGESTED FORENSIC LOG STREAM:\n"
        f"=============================\n"
        f"{chunk_text}\n"
        f"=============================\n\n"
        f"Perform strict Tier-1 SOC incident analysis and extract all IOCs with exact citations now."
    )

    payload = {
        "model": model_name,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 8192,
            "num_predict": 1200,
            "repeat_penalty": 1.15,
        },
    }

    try:
        response = await client.post(OLLAMA_URL, json=payload, timeout=120.0)
        response.raise_for_status()
        res_text = response.json().get("response", "")
        return res_text
    except httpx.TimeoutException:
        return "[WARN]: Chunk analysis timed out in local engine. Continuing with remaining batches."
    except Exception as e:
        return f"[ERROR]: Engine communication error on batch: {e}"


async def process_security_incident(
    file_bytes: bytes,
    filename: str,
    threat_profile: str = "cisco_ise",
    model_name: str = "granite4.1:8b",
) -> str:
    """End-to-End Map-Reduce SOC Triage Pipeline:
    1. Parse artifact (.evtx, .pcap, .log, .pdf, etc.)
    2. Batch events into windowed chunks
    3. Map Phase: Extract indicators per chunk with zero-hallucination rules
    4. Reduce Phase: Synthesize unified Tier-1 Incident Triage Report
    """
    # 1. Forensic Parsing
    print(f"[SOC Engine] Ingesting forensic artifact: {filename} ({len(file_bytes)} bytes)...")
    events = parse_security_artifact(file_bytes, filename)

    if not events:
        print("[SOC Engine] Artifact contains no readable event records.")
        return DEFAULT_CLEAN_SOC_REPORT

    # 2. Windowed Chunking
    chunks = chunk_events(events)
    print(f"[SOC Engine] Dispatched {len(events)} events across {len(chunks)} analysis batches.")

    threat_profile_hints = {
        "cisco_ise": "Priority Detection: Cisco Identity Services Engine Authentication Bypass (CVE-2026-76460)",
        "cobalt_strike": "Priority Detection: Cobalt Strike C2, Beaconing periodicity, Process Injection",
        "log4shell": "Priority Detection: Log4Shell (CVE-2021-44228) & ProxyLogon (CVE-2021-26855) Web RCE",
        "general_triage": "Comprehensive Threat Triage: Identify all anomalies, unauthorized access, and persistence",
    }
    hint = threat_profile_hints.get(threat_profile, threat_profile_hints["cisco_ise"])

    raw_findings = []

    async with httpx.AsyncClient(timeout=None) as client:
        # MAP PHASE: Process chunks
        for idx, chunk in enumerate(chunks):
            print(f"[SOC Engine] Analyzing Batch {idx + 1} of {len(chunks)}...")
            finding = await analyze_soc_chunk(
                client=client,
                chunk_text=chunk,
                filename=filename,
                model_name=model_name,
                system_prompt=SOC_SYSTEM_PROMPT,
                threat_profile_hint=hint,
            )
            raw_findings.append(finding)

        # REDUCE PHASE: Master Report Synthesis
        print("[SOC Engine] Synthesizing Master Tier-1 Incident Triage Report...")
        synthesis_prompt = f"""You are the Master Tier-1 Incident Triage Synthesizer.
Compile the following extracted chunk findings into a SINGLE Master Incident Report in the EXACT required Markdown format.

SYNTHESIS RULES:
{SOC_SYNTHESIS_RULES}

RAW CHUNK FINDINGS TO SYNTHESIZE:
{chr(10).join(raw_findings)}
"""

        payload = {
            "model": model_name,
            "system": SOC_SYSTEM_PROMPT,
            "prompt": synthesis_prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": 8192,
                "num_predict": 2500,
                "repeat_penalty": 1.15,
            },
        }

        try:
            response = await client.post(OLLAMA_URL, json=payload, timeout=180.0)
            response.raise_for_status()
            final_report = response.json().get("response", DEFAULT_CLEAN_SOC_REPORT)
            print("[SOC Engine] Triage Report Synthesis Complete.")
            return final_report
        except Exception as e:
            print(f"[SOC Engine ERROR] Synthesis error: {e}")
            # If reduce fails, return concatenated findings
            return f"# TIER-1 SOC INCIDENT TRIAGE REPORT (PARTIAL EXTRACTION)\n\n" + "\n\n---\n\n".join(raw_findings)
