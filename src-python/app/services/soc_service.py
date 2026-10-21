import io
import json
import httpx
from typing import List, Optional
from app.parsers.artifact_parser import parse_security_artifact
from app.prompts.soc_prompts import (
    SOC_SYSTEM_PROMPT,
    SOC_SYNTHESIS_RULES,
    DEFAULT_CLEAN_SOC_REPORT,
)

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"

# Windowing parameters for large forensic streams (tuned for CPU L3 cache efficiency)
SINGLE_PASS_THRESHOLD = 60
EVENT_CHUNK_SIZE = 40
EVENT_OVERLAP = 4

SOC_CHUNK_EXTRACTOR_PROMPT = """You are a Tier-1 SOC Incident Telemetry Extractor operating in an air-gapped SCIF.
Target Profile: {threat_profile_hint}

Your sole objective is to inspect this log slice for unauthenticated requests, attack payloads, anomalous commands, or indicators matching the target threat profile.

EXTRACTION INSTRUCTIONS:
1. If the log slice contains ONLY normal, benign, or baseline operational telemetry, output EXACTLY:
STATUS: CLEAN
2. If suspicious requests, authentication bypass attempts, command execution, or attack indicators are detected, list ONLY concise bullet points with exact citations:
- [Citation] [IOC_TYPE] Value | Anomaly Description
3. DO NOT output narrative paragraphs, markdown headers, attack timelines, or remediation playbooks. Keep output strictly under 150 words.
"""


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


async def stream_ollama_generate(
    client: httpx.AsyncClient,
    payload: dict,
    timeout_seconds: float = 180.0,
) -> str:
    """Streams tokens from local Ollama to avoid idle read socket timeouts on CPU inference."""
    payload["stream"] = True
    payload["keep_alive"] = "30m"

    # Per-read timeout: 300s prevents prematurely aborting active generations on CPU
    timeout = httpx.Timeout(connect=60.0, read=300.0, write=60.0, pool=60.0)

    full_response: List[str] = []
    try:
        async with client.stream("POST", OLLAMA_URL, json=payload, timeout=timeout) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        full_response.append(token)
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
        return "".join(full_response).strip()
    except httpx.TimeoutException:
        print("[SOC Engine WARN] Local engine timed out waiting for token generation.")
        return "[WARN]: Chunk analysis timed out in local engine. Continuing with remaining batches."
    except Exception as e:
        print(f"[SOC Engine ERROR] Ollama communication failed: {e}")
        return f"[ERROR]: Engine communication error: {e}"


async def get_active_model(client: httpx.AsyncClient, requested_model: Optional[str] = None) -> str:
    """Validates the requested model or resolves to the best available installed model."""
    try:
        res = await client.get(OLLAMA_TAGS_URL, timeout=5.0)
        if res.is_success:
            models_data = res.json().get("models", [])
            installed_names = [m.get("name", "") for m in models_data]

            # 1. Match requested model if provided
            if requested_model and any(requested_model in name for name in installed_names):
                return requested_model

            # 2. Priority order for SOC triage
            for preferred in ["granite4.1:8b", "llama3.2:3b", "llama3.1:8b"]:
                for name in installed_names:
                    if preferred in name:
                        return name

            # 3. Fallback to first available model
            if installed_names:
                return installed_names[0]
    except Exception:
        pass

    return requested_model or "granite4.1:8b"


async def process_security_incident(
    file_bytes: bytes,
    filename: str,
    threat_profile: str = "cisco_ise",
    model_name: Optional[str] = None,
) -> str:
    """End-to-End SOC Triage Pipeline:
    - Standard artifacts (<= 150 events): Direct Single-Pass Analysis (fastest, unified timeline)
    - High-volume artifacts (> 150 events): Streaming Map-Reduce with compact indicator extraction
    """
    # 1. Forensic Parsing
    print(f"[SOC Engine] Ingesting forensic artifact: {filename} ({len(file_bytes)} bytes)...")
    events = parse_security_artifact(file_bytes, filename)

    if not events:
        print("[SOC Engine] Artifact contains no readable event records.")
        return DEFAULT_CLEAN_SOC_REPORT

    threat_profile_hints = {
        "cisco_ise": "Priority Detection: Cisco Identity Services Engine Authentication Bypass (CVE-2026-76460)",
        "cobalt_strike": "Priority Detection: Cobalt Strike C2, Beaconing periodicity, Process Injection",
        "log4shell": "Priority Detection: Log4Shell (CVE-2021-44228) & ProxyLogon (CVE-2021-26855) Web RCE",
        "general_triage": "Comprehensive Threat Triage: Identify all anomalies, unauthorized access, and persistence",
    }
    hint = threat_profile_hints.get(threat_profile, threat_profile_hints["cisco_ise"])

    async with httpx.AsyncClient(timeout=None) as client:
        selected_model = await get_active_model(client, model_name)
        print(f"[SOC Engine] Active inference model: {selected_model}")

        # ---------------------------------------------------------
        # FAST PATH: DIRECT SINGLE-PASS ANALYSIS (<= 150 EVENTS)
        # ---------------------------------------------------------
        if len(events) <= SINGLE_PASS_THRESHOLD:
            print(f"[SOC Engine] Log stream contains {len(events)} events (<= {SINGLE_PASS_THRESHOLD}). Executing Direct Single-Pass Analysis...")
            full_log_text = "\n".join(events)
            user_prompt = (
                f"FORENSIC ARTIFACT FILENAME: {filename}\n"
                f"TARGET PROFILE: {hint}\n\n"
                f"INGESTED FORENSIC LOG STREAM:\n"
                f"=============================\n"
                f"{full_log_text}\n"
                f"=============================\n\n"
                f"Perform strict Tier-1 SOC incident analysis and generate the complete Tier-1 SOC Incident Triage Report now."
            )

            payload = {
                "model": selected_model,
                "system": SOC_SYSTEM_PROMPT,
                "prompt": user_prompt,
                "options": {
                    "temperature": 0.0,
                    "num_ctx": 4096,
                    "num_predict": 1000,
                    "repeat_penalty": 1.15,
                },
            }

            report = await stream_ollama_generate(client, payload)
            if not report or "[WARN]" in report or "[ERROR]" in report:
                print(f"[SOC Engine WARN] Single-pass generation issue, falling back to clean baseline: {report}")
                return report or DEFAULT_CLEAN_SOC_REPORT

            print("[SOC Engine] Single-pass Triage Report Complete.")
            return report

        # ---------------------------------------------------------
        # HIGH-VOLUME PATH: STREAMING MAP-REDUCE (> 150 EVENTS)
        # ---------------------------------------------------------
        chunks = chunk_events(events)
        print(f"[SOC Engine] High-volume stream: {len(events)} events partitioned into {len(chunks)} batches.")

        raw_findings = []
        clean_batches = 0

        # MAP PHASE: Lightweight extraction per chunk
        for idx, chunk in enumerate(chunks):
            print(f"[SOC Engine] Extracting Indicators from Batch {idx + 1} of {len(chunks)}...")
            extractor_prompt = (
                f"FORENSIC LOG STREAM SLICE:\n"
                f"===========================\n"
                f"{chunk}\n"
                f"===========================\n\n"
                f"Extract candidate threat indicators or output 'STATUS: CLEAN'."
            )

            payload = {
                "model": selected_model,
                "system": SOC_CHUNK_EXTRACTOR_PROMPT.format(threat_profile_hint=hint),
                "prompt": extractor_prompt,
                "options": {
                    "temperature": 0.0,
                    "num_ctx": 4096,
                    "num_predict": 250,
                    "repeat_penalty": 1.15,
                },
            }

            finding = await stream_ollama_generate(client, payload)
            if "STATUS: CLEAN" in finding.upper():
                clean_batches += 1
            else:
                raw_findings.append(f"### [Batch {idx + 1} Findings]\n{finding}")

        # If every batch evaluated as clean, return clean report without reducer overhead
        if clean_batches == len(chunks) or not raw_findings:
            print("[SOC Engine] All batches verified benign. Generating Clean Incident Report.")
            return DEFAULT_CLEAN_SOC_REPORT

        # REDUCE PHASE: Master Report Synthesis
        print(f"[SOC Engine] Synthesizing Master Report from {len(raw_findings)} flagged batches...")
        synthesis_prompt = f"""You are the Master Tier-1 Incident Triage Synthesizer.
Compile the following extracted chunk findings into a SINGLE Master Incident Report in the EXACT required Markdown format.

SYNTHESIS RULES:
{SOC_SYNTHESIS_RULES}

FLAGGED CHUNK FINDINGS TO SYNTHESIZE:
{chr(10).join(raw_findings)}
"""

        payload = {
            "model": selected_model,
            "system": SOC_SYSTEM_PROMPT,
            "prompt": synthesis_prompt,
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096,
                "num_predict": 1200,
                "repeat_penalty": 1.15,
            },
        }

        final_report = await stream_ollama_generate(client, payload)
        if not final_report or "[WARN]" in final_report or "[ERROR]" in final_report:
            return f"# TIER-1 SOC INCIDENT TRIAGE REPORT (PARTIAL EXTRACTION)\n\n" + "\n\n---\n\n".join(raw_findings)

        print("[SOC Engine] Master Triage Report Synthesis Complete.")
        return final_report
