# Vault AI: Air-Gapped Document Intelligence Agent

![Rust](https://img.shields.io/badge/rust-%23000000.svg?style=for-the-badge&logo=rust&logoColor=white)
![Tauri](https://img.shields.io/badge/tauri-%2324C8DB.svg?style=for-the-badge&logo=tauri&logoColor=%23FFFFFF)
![Ollama](https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=Ollama&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)

Vault AI is a privacy-first, zero-telemetry desktop intelligence agent engineered for compliance-heavy environments (M&A, legal discovery, private equity). It enables high-performance processing of confidential financial statements and contracts entirely on-device, ensuring zero data egress to public cloud endpoints.

## Systems Architecture

Vault AI bypasses the standard cloud-API wrapper model in favor of a memory-safe, localised execution pipeline.

* **Core Engine:** Written in **Rust** to guarantee unmanaged memory safety, thread-safe concurrent execution, and minimal resource footprint during heavy token generation.
* **Native OS Bindings:** Utilises Tauri to bind the Rust backend to the host operating system, delivering a lightweight, compiled binary that vastly outperforms standard Chromium-based Electron wrappers.
* **Local Inference:** Interfaces directly with local Ollama model runtimes via local sockets. The system architecture enforces a strict zero-trust boundary, ensuring no prompts, context vectors, or documents ever leave the host machine.

## The Zero-Egress Guarantee
Enterprise due diligence requires absolute data sovereignty. Standard LLM architectures present unacceptable compliance risks via third-party telemetry and API logging. Vault AI solves this via:
1. **Air-Gapped Operation:** Capable of running in completely offline environments once the initial model weights are pulled.
2. **Deterministic State Management:** The frontend communicates with the Rust core via strict IPC (Inter-Process Communication) channels, preventing unauthorised network state modifications.

## Installation & Releases

Compiled binaries are available for immediate deployment.

1. Navigate to the [Releases](../../releases) tab.
2. Download the appropriate binary for your system:
   * `VaultAI-Setup.exe` (Windows)
   * `VaultAI.dmg` (macOS)
3. **Prerequisite:** Ensure [Ollama](https://ollama.ai/) is installed and running locally on port `11434`.

## 🛠️ Building from Source

For developers looking to compile the application from source:

### Prerequisites
* Rust toolchain (`rustup`, `cargo`)
* Node.js & npm (or bun/yarn)
* Tauri CLI dependencies (C++ build tools / Xcode command line tools)

### Build Instructions
```bash
# Clone the repository
git clone [https://github.com/souryoghosh07/vault-ai.git](https://github.com/souryoghosh07/vault-ai.git)
cd vault-ai

# Install frontend dependencies
npm install

# Run the application in development mode
npm run tauri dev

# Compile the optimised release binary
npm run tauri build