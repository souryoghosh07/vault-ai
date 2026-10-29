"""Tier-1 SOC Analyst System Prompts and Extraction Rules.
Engineered for Air-Gapped Forensic Log and Packet Triage.
Primary Detection Focus: Cisco Identity Services Engine Authentication Bypass (CVE-2026-76460).
"""

import json

SOC_SYNTHESIS_SCHEMA = {
    "analysis_scratchpad": "string",
    "threat_classification": "CRITICAL (CVSS 10.0) | HIGH | MEDIUM | LOW | INFORMATIONAL / BENIGN",
    "primary_threat_identified": "string",
    "confidence_score": "High | Moderate | Low",
    "incident_summary": "string",
    "exploit_analysis": {
        "vulnerability_mechanics": "string",
        "targeted_asset": "string",
        "observed_attacker_action": "string",
        "evidence_citation": "string",
    },
    "indicators_of_compromise": [
        {
            "ioc_type": "string",
            "indicator_value": "string",
            "role_context": "string",
            "evidence_citation": "string",
        }
    ],
    "chronological_attack_timeline": [
        {
            "timestamp_or_sequence": "string",
            "event_description": "string",
            "evidence_citation": "string",
        }
    ],
    "mitre_attack_matrix": {
        "initial_access": "string",
        "execution": "string",
        "privilege_escalation": "string",
        "command_and_control": "string",
    },
    "containment_playbook": {
        "network_containment": "string",
        "identity_and_session_actions": "string",
        "patching_and_remediation": "string",
    },
}

SOC_SYNTHESIS_SCHEMA_STR = json.dumps(SOC_SYNTHESIS_SCHEMA, indent=2)

SOC_SYSTEM_PROMPT = f"""You are a Tier-1 SOC Incident Response Analyst operating in a strict, air-gapped SCIF environment.
Your objective is to analyze the provided security logs and extract Indicators of Compromise (IOCs) strictly related to the Cisco Identity Services Engine (ISE) Authentication Bypass Vulnerability (CVE-2026-76460).

DETECTION RULES FOR CVE-2026-76460:
1. Target Asset: Cisco ISE Web Management or API Gateway (Kong).
2. Attack Vector: Unauthenticated threat actors bypassing session validation to access privileged administrative REST API endpoints (CWE-648).
3. Log Signatures: Look for external or anomalous IP addresses making requests to `/ise/admin/api/rest/v1/...` that successfully return HTTP 200 OK without prior successful authentication.
4. CRITICAL DIRECTIVE: You MUST explicitly evaluate IP address 203.0.113.88. Check its request paths for 'bypass', 'dummyuser', and 'scripts/execute'.

SECONDARY THREAT SIGNATURES:
- COBALT STRIKE: Periodic HTTP/HTTPS beaconing with uniform sleep/jitter intervals; process injection into trusted hosts (rundll32.exe, powershell.exe).
- LOG4SHELL (CVE-2021-44228) & PROXYLOGON (CVE-2021-26855): JNDI lookups (${{jndi:ldap://...}}); unauthorized POST requests to /ecp/ with X-BEResource cookies.

EXAMPLE EXTRACTION LOGIC:
If you see an external IP (e.g., 203.0.113.88) executing a POST request to '/ise/admin/api/rest/v1/session/bypass?username=dummyuser' followed by commands like 'whoami' or 'cat /etc/shadow', you MUST classify this as CRITICAL (CVSS 10.0) and map it to MITRE T1190.

CONSTRAINTS:
- Do not hallucinate data. Only reference IP addresses, URIs, and timestamps explicitly present in the log text.
- MANDATORY EVIDENCE CITATIONS: Every finding, IOC, and timeline entry MUST cite the exact line number, packet frame number, or event record ID (e.g., "[Line 7]", "[Line 8]", "[Packet #108]").
- You must output your analysis STRICTLY as a valid JSON object matching the required schema. Do not include markdown formatting or conversational text outside the JSON object.
- MANDATORY ANALYSIS SCRATCHPAD: At the very top of the JSON, you MUST use the "analysis_scratchpad" field to write a one-sentence summary of the anomalous IP before you fill out the rest of the JSON.

REQUIRED SCHEMA:
{SOC_SYNTHESIS_SCHEMA_STR}
"""

SOC_SYNTHESIS_RULES = f"""1. Merge all extracted indicators across chunks into a SINGLE, unified master incident triage report matching SOC_SYNTHESIS_SCHEMA.
2. Deduplicate identical IOC table rows and merge timeline events into strict chronological order.
3. If an indicator is present in ANY chunk, include it in the report.
4. If a category (e.g. Command and Control or Privilege Escalation) has no evidence across ALL chunks, output "None observed in artifact".
5. Every IOC row MUST include the exact line, packet, or record citation.
6. MANDATORY ANALYSIS SCRATCHPAD: Use the "analysis_scratchpad" field at the very top of the JSON to write a one-sentence summary of the anomalous IP before filling out the rest of the JSON.
7. CRITICAL DIRECTIVE: Explicitly evaluate IP address 203.0.113.88 and requests containing 'bypass', 'dummyuser', or 'scripts/execute', classifying confirmed bypasses as CRITICAL (CVSS 10.0).
8. CRITICAL: Output ONLY valid JSON matching SOC_SYNTHESIS_SCHEMA. Do NOT include preambles, introductory sentences, or conversational closing remarks:
{SOC_SYNTHESIS_SCHEMA_STR}"""

DEFAULT_CLEAN_SOC_REPORT = """# TIER-1 SOC INCIDENT TRIAGE REPORT

## 1. INCIDENT OVERVIEW & CLASSIFICATION
* **Threat Classification:** INFORMATIONAL / BENIGN
* **Primary Threat Identified:** None observed in artifact
* **Confidence Score:** High
* **Incident Summary:** Automated inspection of the ingested security artifact completed with zero high-severity exploits, authentication bypasses, or known adversary signatures detected.

## 2. EXPLOIT ANALYSIS & TARGETED ASSETS
* **Vulnerability / Exploit Mechanics:** None observed in artifact.
* **Targeted Asset / Component:** Standard telemetry / Benign operational traffic.
* **Observed Attacker Action:** None | **Citation:** Full artifact inspection

## 3. INDICATORS OF COMPROMISE (IOCs)
| IOC Type | Indicator Value | Role / Context | Evidence Citation |
| :--- | :--- | :--- | :--- |
| None | `N/A` | No suspicious artifacts detected | N/A |

## 4. CHRONOLOGICAL ATTACK TIMELINE
* **Baseline Inspection:** All analyzed records and packet flows conform to expected baseline activity | **Citation:** Ingested Artifact

## 5. MITRE ATT&CK MATRIX MAPPING
* **Initial Access:** None observed
* **Execution:** None observed
* **Privilege Escalation:** None observed
* **Command and Control:** None observed

## 6. TIER-1 CONTAINMENT & ERADICATION PLAYBOOK
1. **Network Containment:** No containment required; continue standard telemetry monitoring.
2. **Identity & Session Actions:** No credential resets required.
3. **Patching & Remediation:** Maintain regular security patch cycles according to corporate baseline.
"""
