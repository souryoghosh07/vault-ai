# Vault AI: Air-Gapped Tier-1 SOC Analyst Workbench

![Rust](https://img.shields.io/badge/rust-%23000000.svg?style=for-the-badge&logo=rust&logoColor=white)
![Tauri](https://img.shields.io/badge/tauri-%2324C8DB.svg?style=for-the-badge&logo=tauri&logoColor=%23FFFFFF)
![Ollama](https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=Ollama&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)

Vault AI is a privacy-first, zero-telemetry desktop intelligence agent engineered for air-gapped forensic incident response teams and Tier-1 Security Operations Centers (SOC). It enables high-performance triage of event logs, Windows Event Logs (`.evtx`), network packet captures (`.pcap`, `.pcapng`), and syslog streams entirely on-device, ensuring zero data egress to public endpoints.

---

## Targeted High-Severity Threat Profiles

Vault AI's reasoning engine features hardcoded, deterministic Tier-1 SOC detection profiles:

1. **Cisco Identity Services Engine (ISE) Authentication Bypass (CVE-2026-76460 / CWE-648)**:
   - Evaluates unauthenticated API requests to Kong API Gateway routes (`/api/v1/...`, `/ise/...`, `/admin/...`).
   - Detects missing/anomalous authorization headers, session tokens, and immediate root shell command spawning (`bash`, `sh`, `sudo`).
   - Flags suspicious outbound C2 network egress from ISE nodes.
2. **Cobalt Strike Beaconing & C2**:
   - Detects uniform sleep/jitter beaconing intervals, named pipe IPC, and process injection into trusted hosts (`rundll32.exe`, `powershell.exe`).
3. **Log4Shell (CVE-2021-44228) & ProxyLogon (CVE-2021-26855)**:
   - Scans web server telemetry for `${jndi:ldap://...}` headers, outbound LDAP/RMI requests, and Exchange `/ecp/` SSRF webshell deployments.
4. **Universal Event Log Triage**:
   - Ingests raw Windows EVTX records (Logon bursts Event 4625, Service installation Event 7045), PCAP TCP/UDP streams, and syslog lines.

---

## Systems Architecture

Vault AI bypasses the standard cloud-API model in favor of an offline, memory-safe execution pipeline:

* **Core Desktop Shell:** Written in **Rust / Tauri v2** to guarantee memory safety, thread-safe concurrent execution, and native OS windowing without Chromium Electron overhead.
* **Forensic Ingestion Engine:** Native Python parsers (`python-evtx` for binary event logs, `dpkt` for packet captures, and IBM Docling for threat advisory PDFs) with zero cloud dependencies (`HF_HUB_OFFLINE=1`).
* **Local Inference Pipeline:** Interfaces directly with local Ollama runtimes (`granite4.1:8b`) via local sockets. The system enforces strict anti-hallucination rules requiring exact evidence citations (`[Line X]`, `[Packet #Y]`, `[EVTX Record #Z]`).

---

## 🛠️ Building & Running from Source

### Prerequisites
* Rust toolchain (`rustup`, `cargo`)
* Node.js & npm (v18+)
* Python 3.11+
* [Ollama](https://ollama.ai/) running locally on port `11434` with `granite4.1:8b`

### Run in Development Mode
```bash
# Clone the repository
git clone https://github.com/souryoghosh07/vault-ai.git
cd vault-ai

# Install frontend dependencies
npm install

# Run the desktop application
npm run tauri dev
```

### Compile Release Binary
```bash
npm run tauri build
```