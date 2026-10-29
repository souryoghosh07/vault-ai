import io
import json
import httpx
from typing import List, Optional, Union
from app.parsers.artifact_parser import parse_security_artifact
from app.prompts.soc_prompts import (
    SOC_SYSTEM_PROMPT,
    SOC_SYNTHESIS_SCHEMA,
    SOC_SYNTHESIS_RULES,
    DEFAULT_CLEAN_SOC_REPORT,
)

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"

# Windowing parameters for large forensic streams (tuned for CPU L3 cache efficiency)
SINGLE_PASS_THRESHOLD = 60
EVENT_CHUNK_SIZE = 40
EVENT_OVERLAP = 4

# Noise signatures to filter out benign noise and prevent attention dilution in sub-3B models
NOISE_SIGNATURES = [
    "Prometheus", 
    "ISE-Internal-Agent", 
    "Cisco-Catalyst-9300-Edge", 
    "ISE-HealthCheck"
]


def compress_artifact_context(raw_log: str) -> str:
    """Strips known benign telemetry to preserve LLM attention span on constrained hardware."""
    filtered_lines = []
    for line in raw_log.split('\n'):
        if line.strip() == "" or line.startswith("#"):
            continue  # Skip comments and blanks
            
        # If the line DOES NOT contain benign noise, keep it
        if not any(noise in line for noise in NOISE_SIGNATURES):
            filtered_lines.append(line)
            
    return '\n'.join(filtered_lines)

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


DEPRECATED_MODELS = {"llama3.1", "glm-ocr", "moondream", "granite4.1"}


async def get_active_model(client: httpx.AsyncClient, requested_model: Optional[str] = None) -> str:
    """Validates the requested model or resolves to the best available installed model."""
    try:
        res = await client.get(OLLAMA_TAGS_URL, timeout=5.0)
        if res.is_success:
            models_data = res.json().get("models", [])
            installed_names = [m.get("name", "") for m in models_data]

            # Filter out deprecated models
            valid_installed = [
                name for name in installed_names
                if not any(dep in name.lower() for dep in DEPRECATED_MODELS)
            ]

            # 1. Match requested model if provided and valid
            if requested_model and any(requested_model in name for name in valid_installed):
                return requested_model

            # 2. Priority order for SOC triage: Llama 3.2 3B & SmolLM2 1.7B
            for preferred in ["llama3.2:3b", "smollm2:1.7b", "smollm2"]:
                for name in valid_installed:
                    if preferred in name:
                        return name

            # 3. Fallback to first valid model
            if valid_installed:
                return valid_installed[0]
    except Exception:
        pass

    return requested_model or "llama3.2:3b"


def robust_json_loads(raw_text: str) -> dict:
    """Safely parses JSON, attempting automatic repair if truncated by LLM token limits."""
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt progressive closing of open structures
    repaired = text
    for _ in range(10):
        for closer in ["}", "\"]}", "]}", "\"}", "}]}", "\"\n}", "\"\n}\n}"]:
            try:
                return json.loads(repaired + closer)
            except Exception:
                pass
        # Trim back to last comma or newline to remove truncated tokens
        last_delim = max(repaired.rfind(","), repaired.rfind("\n"))
        if last_delim > 0:
            repaired = repaired[:last_delim].rstrip().rstrip(",")
        else:
            break

    return json.loads(text)  # Re-raise standard JSONDecodeError if repair unsuccessful


def format_soc_output_to_markdown(raw_output: str) -> str:
    """If raw_output is a JSON string conforming to SOC_SYNTHESIS_SCHEMA,
    formats it into the canonical Tier-1 SOC Markdown report with scratchpad callout.
    Otherwise returns raw_output.
    """
    if not raw_output:
        return DEFAULT_CLEAN_SOC_REPORT

    try:
        data = robust_json_loads(raw_output)
        if not isinstance(data, dict):
            return raw_output
    except Exception:
        return raw_output

    scratchpad = str(data.get("analysis_scratchpad", "")).strip()
    classification = str(data.get("threat_classification", "INFORMATIONAL / BENIGN")).strip()
    primary_threat = str(data.get("primary_threat_identified", "None observed in artifact")).strip()
    confidence = str(data.get("confidence_score", "High")).strip()
    summary = str(data.get("incident_summary", "Automated inspection completed.")).strip()

    exploit = data.get("exploit_analysis", {})
    if isinstance(exploit, dict):
        vuln = exploit.get("vulnerability_mechanics", "None observed in artifact.")
        asset = exploit.get("targeted_asset", "Standard telemetry / Benign operational traffic.")
        action = exploit.get("observed_attacker_action", "None")
        citation = exploit.get("evidence_citation", "Full artifact inspection")
    else:
        vuln, asset, action, citation = "None observed in artifact.", "N/A", "None", "N/A"

    # Indicators of Compromise
    iocs = data.get("indicators_of_compromise", [])
    ioc_rows = []
    if isinstance(iocs, list) and len(iocs) > 0:
        for ioc in iocs:
            if isinstance(ioc, dict):
                t = ioc.get("ioc_type", "N/A")
                v = ioc.get("indicator_value", "N/A")
                r = ioc.get("role_context", "N/A")
                c = ioc.get("evidence_citation", "N/A")
                ioc_rows.append(f"| {t} | `{v}` | {r} | {c} |")
    if not ioc_rows:
        ioc_rows.append("| None | `N/A` | No suspicious artifacts detected | N/A |")

    # Timeline
    timeline = data.get("chronological_attack_timeline", [])
    timeline_lines = []
    if isinstance(timeline, list) and len(timeline) > 0:
        for entry in timeline:
            if isinstance(entry, dict):
                ts = entry.get("timestamp_or_sequence", "Event")
                desc = entry.get("event_description", "")
                cite = entry.get("evidence_citation", "")
                timeline_lines.append(f"* **{ts}:** {desc} | **Citation:** {cite}")
    if not timeline_lines:
        timeline_lines.append("* **Baseline Inspection:** All analyzed records and packet flows conform to expected baseline activity | **Citation:** Ingested Artifact")

    # MITRE ATT&CK Matrix Mapping
    mitre = data.get("mitre_attack_matrix", {})
    if not isinstance(mitre, dict):
        mitre = {}
    init_access = mitre.get("initial_access", "None observed")
    execution = mitre.get("execution", "None observed")
    priv_esc = mitre.get("privilege_escalation", "None observed")
    c2 = mitre.get("command_and_control", "None observed")

    # Containment Playbook
    containment = data.get("containment_playbook", {})
    if not isinstance(containment, dict):
        containment = {}
    net_contain = containment.get("network_containment", "No containment required; continue standard telemetry monitoring.")
    id_contain = containment.get("identity_and_session_actions", "No credential resets required.")
    patching = containment.get("patching_and_remediation", "Maintain regular security patch cycles according to corporate baseline.")

    scratchpad_block = f"> **Analyst Scratchpad:** {scratchpad}\n\n" if scratchpad else ""

    md = f"""# TIER-1 SOC INCIDENT TRIAGE REPORT

{scratchpad_block}## 1. INCIDENT OVERVIEW & CLASSIFICATION
* **Threat Classification:** {classification}
* **Primary Threat Identified:** {primary_threat}
* **Confidence Score:** {confidence}
* **Incident Summary:** {summary}

## 2. EXPLOIT ANALYSIS & TARGETED ASSETS
* **Vulnerability / Exploit Mechanics:** {vuln}
* **Targeted Asset / Component:** {asset}
* **Observed Attacker Action:** {action} | **Citation:** {citation}

## 3. INDICATORS OF COMPROMISE (IOCs)
| IOC Type | Indicator Value | Role / Context | Evidence Citation |
| :--- | :--- | :--- | :--- |
{chr(10).join(ioc_rows)}

## 4. CHRONOLOGICAL ATTACK TIMELINE
{chr(10).join(timeline_lines)}

## 5. MITRE ATT&CK MATRIX MAPPING
* **Initial Access:** {init_access}
* **Execution:** {execution}
* **Privilege Escalation:** {priv_esc}
* **Command and Control:** {c2}

## 6. TIER-1 CONTAINMENT & ERADICATION PLAYBOOK
1. **Network Containment:** {net_contain}
2. **Identity & Session Actions:** {id_contain}
3. **Patching & Remediation:** {patching}
"""
    return md


async def process_security_incident(
    file_bytes: Union[bytes, bytearray, str],
    filename: str = "security_artifact.log",
    threat_profile: str = "cisco_ise",
    model_name: Optional[str] = None,
) -> str:
    """End-to-End SOC Triage Pipeline:
    - Context Compression: Deterministically strips known benign telemetry (noise) to protect sub-3B LLM attention.
    - Standard artifacts (<= 60 events): Direct Single-Pass Analysis (fastest, unified timeline)
    - High-volume artifacts (> 60 events): Streaming Map-Reduce with compact indicator extraction
    """
    if isinstance(file_bytes, str):
        events = [line.strip() for line in file_bytes.splitlines() if line.strip()]
    else:
        # 1. Forensic Parsing
        print(f"[SOC Engine] Ingesting forensic artifact: {filename} ({len(file_bytes)} bytes)...")
        events = parse_security_artifact(file_bytes, filename)

    if not events:
        print("[SOC Engine] Artifact contains no readable event records.")
        return DEFAULT_CLEAN_SOC_REPORT

    # 2. Context Compression: Strip known benign noise signatures
    raw_joined = "\n".join(events)
    compressed_text = compress_artifact_context(raw_joined)
    compressed_events = [line for line in compressed_text.split('\n') if line.strip()]

    # If the artifact only contained known benign telemetry, return clean baseline immediately
    if not compressed_events:
        print("[SOC Engine] Artifact contains only baseline telemetry (noise filtered). Returning clean baseline report.")
        return DEFAULT_CLEAN_SOC_REPORT

    # Replace events with compressed pure-signal events
    events = compressed_events

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
                "format": "json",
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

            report = format_soc_output_to_markdown(report)
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
            "format": "json",
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

        final_report = format_soc_output_to_markdown(final_report)
        print("[SOC Engine] Master Triage Report Synthesis Complete.")
        return final_report


def process_security_incident_sync(log_text: str, threat_profile: str = "cisco_ise", model_name: str = "llama3.2:3b") -> dict:
    """Synchronous interface matching the optimization plan specification.
    Strips benign telemetry via compress_artifact_context and queries the local LLM.
    Returns a dict adhering to SOC_SYNTHESIS_SCHEMA.
    """
    if threat_profile != "cisco_ise":
        raise ValueError("Only 'cisco_ise' profile is active for this deployment branch.")

    # Compress the log before handing it to the LLM
    compressed_log = compress_artifact_context(log_text)
    if not compressed_log.strip():
        return {
            "analysis_scratchpad": "Artifact contains only benign telemetry.",
            "threat_classification": "INFORMATIONAL / BENIGN",
            "primary_threat_identified": "None observed in artifact",
            "confidence_score": "High",
            "incident_summary": "No anomalous indicators detected after noise filtering."
        }

    full_prompt = f"{SOC_SYSTEM_PROMPT}\n\nREQUIRED SCHEMA:\n{json.dumps(SOC_SYNTHESIS_SCHEMA, indent=2)}\n\nFILTERED LOG DATA:\n{compressed_log}"
    
    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "num_predict": 1000,
            "repeat_penalty": 1.15
        }
    }
    
    with httpx.Client(timeout=120.0) as client:
        response = client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        result_text = response.json().get("response", "{}")
    
    try:
        return robust_json_loads(result_text)
    except Exception:
        return {"error": "Local LLM failed to output valid JSON schema.", "raw_output": result_text}

