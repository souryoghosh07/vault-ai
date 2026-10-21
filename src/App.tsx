import React, { useState, useRef, useEffect } from 'react';
import { save } from '@tauri-apps/plugin-dialog';
import { writeTextFile } from '@tauri-apps/plugin-fs';

type ThreatProfile = 'cisco_ise' | 'cobalt_strike' | 'log4shell' | 'general_triage';

interface ProfileMeta {
  id: ThreatProfile;
  label: string;
  badge: string;
  description: string;
  rules: string[];
}

const THREAT_PROFILES: ProfileMeta[] = [
  {
    id: 'cisco_ise',
    label: 'Cisco ISE (CVE-2026-76460)',
    badge: 'CVSS 10.0',
    description: 'Detection of unauthenticated REST API abuse against Cisco ISE & Kong Gateway leading to root privilege command execution (CWE-648).',
    rules: [
      'Kong API Gateway access anomalies (ise-kong/access.log)',
      'Unauthenticated requests to /api/v1/..., /ise/..., or /admin/...',
      'Missing or spoofed Authorization headers and bypass tokens',
      'Immediate root shell execution (bash, sh, sudo) following API hits',
      'Anomalous outbound C2 network egress from ISE nodes'
    ]
  },
  {
    id: 'cobalt_strike',
    label: 'Cobalt Strike Beacon',
    badge: 'C2 THREAT',
    description: 'Detection of periodic C2 beaconing, process injection, named pipes, and suspicious command staging.',
    rules: [
      'Uniform sleep / jitter HTTP request intervals',
      'Process injection into trusted hosts (rundll32.exe, dllhost.exe)',
      'Named pipe IPC creation patterns',
      'Staged shellcode memory allocations & Base64 payloads'
    ]
  },
  {
    id: 'log4shell',
    label: 'Log4Shell & ProxyLogon',
    badge: 'CRITICAL RCE',
    description: 'Detection of JNDI LDAP/RMI lookup injections (CVE-2021-44228) and Exchange ProxyLogon SSRF / webshell drops (CVE-2021-26855).',
    rules: [
      '${jndi:ldap://...} and ${jndi:rmi://...} string injections in headers',
      'Outbound LDAP/RMI connections initiated by web servers',
      'Exchange /ecp/ requests containing X-BEResource cookies',
      'Arbitrary file writes in OAB / inetpub web-accessible directories'
    ]
  },
  {
    id: 'general_triage',
    label: 'Universal Event Triage',
    badge: 'SOC TRIAGE',
    description: 'Automated threat triage across Windows EVTX logs, PCAP packet streams, and Linux syslog files.',
    rules: [
      'Burst failed logons & password spraying (Event 4625)',
      'Suspicious service installations & privilege escalation (Event 7045)',
      'Anomalous port scanning and lateral movement network flows',
      'Encoded PowerShell & suspicious script interpreter invocations'
    ]
  }
];

export default function App() {
  // --- ENGINE STATUS STATES ---
  const [modelStatus, setModelStatus] = useState<string>("Connecting to SOC Engine...");
  const [downloadProgress, setDownloadProgress] = useState<number>(0);
  const [isReady, setIsReady] = useState<boolean>(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("granite4.1:8b");

  // --- APP STATES ---
  const [activeProfile, setActiveProfile] = useState<ThreatProfile>('cisco_ise');
  const [file, setFile] = useState<File | null>(null);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // --- EFFECT: INITIALIZE & POLL ENGINES ---
  useEffect(() => {
    let isMounted = true;

    const checkHealth = async () => {
      let apiOk = false;
      let ollamaOk = false;

      // 1. Check Python SOC API on port 8000
      try {
        const apiRes = await fetch("http://127.0.0.1:8000/health");
        if (apiRes.ok) {
          apiOk = true;
        }
      } catch (_) {
        apiOk = false;
      }

      // 2. Check Ollama on port 11434
      try {
        const tagsResponse = await fetch("http://127.0.0.1:11434/api/tags");
        if (tagsResponse.ok) {
          const tagsData = await tagsResponse.json();
          const models: string[] = tagsData.models?.map((m: any) => m.name) || [];

          if (models.length > 0) {
            if (isMounted) {
              setAvailableModels(models);
              setSelectedModel(prev => {
                if (prev && models.includes(prev)) return prev;
                if (models.includes("granite4.1:8b")) return "granite4.1:8b";
                if (models.includes("llama3.2:3b")) return "llama3.2:3b";
                return models[0];
              });
            }
            ollamaOk = true;
          } else {
            if (isMounted) setModelStatus("Downloading Granite 4.1 Model (First Boot Only)...");
            try {
              const pullResponse = await fetch("http://127.0.0.1:11434/api/pull", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: "granite4.1:8b" })
              });
              const reader = pullResponse.body?.getReader();
              if (reader) {
                while (true) {
                  const { done, value } = await reader.read();
                  if (done) break;
                  const chunk = new TextDecoder().decode(value);
                  const lines = chunk.split("\n").filter(Boolean);
                  for (const line of lines) {
                    try {
                      const json = JSON.parse(line);
                      if (json.total && json.completed) {
                        const percentage = Math.round((json.completed / json.total) * 100);
                        if (isMounted) setDownloadProgress(percentage);
                      }
                    } catch (_) {}
                  }
                }
                ollamaOk = true;
              }
            } catch (_) {}
          }
        }
      } catch (_) {
        ollamaOk = false;
      }

      if (!isMounted) return;

      if (apiOk && ollamaOk) {
        setModelStatus("SOC Engine & Ollama Online (Air-Gapped)");
        setIsReady(true);
      } else if (apiOk && !ollamaOk) {
        setModelStatus("SOC Engine Online | Awaiting Ollama (Port 11434)...");
        setIsReady(true);
      } else if (!apiOk && ollamaOk) {
        setModelStatus("Ollama Online | Awaiting SOC API (Port 8000)...");
        setIsReady(false);
      } else {
        setModelStatus("Connecting to Local Engines (Ports 8000 & 11434)...");
        setIsReady(false);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 3000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setReport(null);
      setError(null);
    }
  };

  const getFileBadge = (filename: string) => {
    const lower = filename.toLowerCase();
    if (lower.endsWith('.evtx')) return { label: 'WINDOWS EVTX', color: '#3B82F6' };
    if (lower.endsWith('.pcap') || lower.endsWith('.pcapng') || lower.endsWith('.cap')) return { label: 'PCAP CAPTURE', color: '#8B5CF6' };
    if (lower.endsWith('.pdf')) return { label: 'PDF REPORT', color: '#EC4899' };
    if (lower.endsWith('.json')) return { label: 'JSON TELEMETRY', color: '#10B981' };
    return { label: 'SECURITY LOG', color: '#F59E0B' };
  };

  // NATIVE TAURI SAVE (MARKDOWN)
  const downloadReport = async () => {
    if (!report) return;
    try {
      const suggestedName = `${file?.name.replace(/\.[^/.]+$/, "") || 'Incident'}_SOC_Triage.md`;
      const filePath = await save({
        filters: [{ name: 'Markdown', extensions: ['md'] }],
        defaultPath: suggestedName,
      });

      if (filePath) {
        await writeTextFile(filePath, report);
      }
    } catch (err: any) {
      setError(`Failed to save report: ${err.message || err}`);
    }
  };

  // NATIVE BROWSER PRINT ENGINE (PDF)
  const saveAsPDF = () => {
    window.print();
  };

  const runSOCTriage = async () => {
    if (!file) {
      setError("Please attach a forensic artifact (.evtx, .pcap, .log, .pdf) first.");
      return;
    }

    setIsScanning(true);
    setError(null);
    setReport(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("threat_profile", activeProfile);
    if (selectedModel) {
      formData.append("model_name", selectedModel);
    }

    try {
      const response = await fetch("http://127.0.0.1:8000/api/soc/analyze", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errDetail = await response.text();
        throw new Error(`Server returned ${response.status}: ${errDetail}`);
      }

      const data = await response.json();
      setReport(data.report_markdown);
    } catch (err: any) {
      if (err.message?.includes("Failed to fetch") || err.message?.includes("NetworkError") || err.message?.includes("Load failed")) {
        setError("Cannot connect to Python SOC Engine on http://127.0.0.1:8000. Ensure the backend is running via 'npm run dev' or 'python run_api.py'.");
      } else {
        setError(err.message || "Failed to communicate with local SOC engine.");
      }
    } finally {
      setIsScanning(false);
    }
  };

  const selectedProfileMeta = THREAT_PROFILES.find(p => p.id === activeProfile)!;

  // Custom Report Formatter with Markdown Table, Citations & Severity Badges
  const renderReport = (text: string) => {
    const lines = text.split('\n');
    const rendered: React.ReactNode[] = [];
    let inTable = false;
    let tableRows: string[][] = [];

    const flushTable = (keyPrefix: number) => {
      if (tableRows.length === 0) return;
      const headers = tableRows[0];
      const dataRows = tableRows.slice(1);

      rendered.push(
        <div key={`table-wrapper-${keyPrefix}`} style={styles.tableWrapper}>
          <table style={styles.table}>
            <thead>
              <tr>
                {headers.map((th, hIdx) => (
                  <th key={hIdx} style={styles.th}>{th.trim()}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dataRows.map((row, rIdx) => (
                <tr key={rIdx} style={rIdx % 2 === 0 ? styles.trEven : styles.trOdd}>
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} style={styles.td}>
                      <span dangerouslySetInnerHTML={{
                        __html: cell.trim()
                          .replace(/`([^`]+)`/g, '<code style="background-color: #F1F5F9; color: #0F172A; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.85em;">$1</code>')
                          .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                      }} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableRows = [];
      inTable = false;
    };

    lines.forEach((line, index) => {
      const trimmed = line.trim();

      // Table line detection
      if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
        // Skip markdown separator lines like | :--- | :--- |
        if (/^\|[\s\-:]+(\|[\s\-:]+)+\|$/.test(trimmed)) {
          return;
        }
        const cells = trimmed.split('|').slice(1, -1);
        tableRows.push(cells);
        inTable = true;
        return;
      } else if (inTable) {
        flushTable(index);
      }

      if (line.startsWith('# ')) {
        rendered.push(<h1 key={index} style={styles.h1}>{line.replace('# ', '')}</h1>);
        return;
      }
      if (line.startsWith('## ')) {
        rendered.push(<h2 key={index} style={styles.h2}>{line.replace('## ', '')}</h2>);
        return;
      }
      if (line.startsWith('### ')) {
        rendered.push(<h3 key={index} style={styles.h3}>{line.replace('### ', '')}</h3>);
        return;
      }

      if (line.startsWith('* ') || line.startsWith('- ') || /^\d+\.\s/.test(line)) {
        let content = line.replace(/^(\*|-|\d+\.)\s+/, '');

        // Severity detection
        let severityBadge: React.ReactNode = null;
        if (content.includes('CRITICAL (CVSS 10.0)')) {
          severityBadge = <span style={{ ...styles.badge, backgroundColor: '#FEE2E2', color: '#991B1B', borderColor: '#F87171' }}>CRITICAL (CVSS 10.0)</span>;
          content = content.replace('CRITICAL (CVSS 10.0)', '');
        } else if (content.includes('HIGH')) {
          severityBadge = <span style={{ ...styles.badge, backgroundColor: '#FFEDD5', color: '#9A3412', borderColor: '#FB923C' }}>HIGH SEVERITY</span>;
          content = content.replace('HIGH', '');
        }

        // Citation extraction
        const citationMatch = content.match(/Citation:\s*(.*)/i) || content.match(/\[(Line\s*\d+|Packet\s*#\d+|Record\s*#\d+|EVTX\s*Record\s*#\d+|Page\s*\d+)\]/i);

        if (citationMatch) {
          const splitText = content.split(citationMatch[0]);
          rendered.push(
            <li key={index} style={styles.listItem}>
              {severityBadge}
              <span dangerouslySetInnerHTML={{ __html: splitText[0].replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code style="background-color: #F1F5F9; color: #0F172A; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.85em;">$1</code>') }} />
              <span style={styles.citationBadge}>{citationMatch[0]}</span>
              <span dangerouslySetInnerHTML={{ __html: splitText[1].replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }} />
            </li>
          );
          return;
        }

        rendered.push(
          <li key={index} style={styles.listItem}>
            {severityBadge}
            <span dangerouslySetInnerHTML={{ __html: content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code style="background-color: #F1F5F9; color: #0F172A; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.85em;">$1</code>') }} />
          </li>
        );
        return;
      }

      if (trimmed === '') {
        rendered.push(<br key={index} />);
        return;
      }

      rendered.push(
        <p key={index} style={styles.text} dangerouslySetInnerHTML={{
          __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code style="background-color: #F1F5F9; color: #0F172A; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.85em;">$1</code>')
        }} />
      );
    });

    if (inTable) {
      flushTable(lines.length);
    }

    return rendered;
  };

  return (
    <>
      {/* INJECTED PRINT STYLES FOR NATIVE PDF EXPORT */}
      <style>
        {`
          @media print {
            .no-print { display: none !important; }
            body { background-color: #FFFFFF !important; }
            #app-container { padding: 0 !important; gap: 0 !important; }
            #report-container { 
              box-shadow: none !important; 
              border: none !important; 
              padding: 0 !important; 
              overflow: visible !important;
            }
          }
        `}
      </style>

      <div id="app-container" style={styles.container}>
        {/* LEFT SIDEBAR: Controls */}
        <div className="no-print" style={styles.sidebar}>
          <div style={styles.brandPanel}>
            <div style={styles.brandRow}>
              <div style={styles.brandTitle}>Vault AI</div>
              <span style={styles.socBadge}>TIER-1 SOC</span>
            </div>
            <div style={styles.subTitle}>Air-Gapped Forensic Intelligence Workbench</div>

            {/* DYNAMIC STATUS BADGE */}
            <div style={{
              ...styles.statusBadge,
              backgroundColor: isReady ? '#ECFDF5' : '#FEF3C7',
              borderColor: isReady ? '#10B981' : '#F59E0B',
              color: isReady ? '#065F46' : '#92400E'
            }}>
              <span style={{ ...styles.statusDot, backgroundColor: isReady ? '#10B981' : '#D97706' }}></span>
              {modelStatus}
            </div>

            {/* DOWNLOAD PROGRESS BAR */}
            {downloadProgress > 0 && !isReady && (
              <div style={styles.progressBarContainer}>
                <div style={{ ...styles.progressBar, width: `${downloadProgress}%` }}></div>
              </div>
            )}
          </div>

          {/* LOCAL INFERENCE MODEL SELECTOR */}
          <div style={styles.panel}>
            <div style={styles.panelTitle}>Local Inference Model</div>
            {availableModels.length > 0 ? (
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={isScanning}
                style={styles.modelSelect}
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>
                    {m} {m.includes('3.2') || m.includes('3b') ? '⚡ (Fast CPU)' : m.includes('granite') ? '🛡️ (SOC Default)' : ''}
                  </option>
                ))}
              </select>
            ) : (
              <div style={styles.modelSelectPlaceholder}>Detecting local Ollama models...</div>
            )}
          </div>

          {/* THREAT PROFILE SELECTOR */}
          <div style={styles.panel}>
            <div style={styles.panelTitle}>Active Threat Profile</div>
            <div style={styles.profileSelectGroup}>
              {THREAT_PROFILES.map((p) => (
                <button
                  key={p.id}
                  style={activeProfile === p.id ? styles.activeProfileButton : styles.inactiveProfileButton}
                  onClick={() => setActiveProfile(p.id)}
                  disabled={isScanning}
                >
                  <div style={styles.profileButtonHeader}>
                    <span>{p.label}</span>
                    <span style={{
                      ...styles.profileTag,
                      backgroundColor: activeProfile === p.id ? '#0F172A' : '#E2E8F0',
                      color: activeProfile === p.id ? '#F8FAFC' : '#475569'
                    }}>{p.badge}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* ARTIFACT INGESTION */}
          <div style={styles.panel}>
            <div style={styles.panelTitle}>Forensic Artifact</div>

            <input
              type="file"
              accept=".evtx,.pcap,.pcapng,.cap,.log,.txt,.json,.csv,.xml,.syslog,.pdf"
              onChange={handleFileChange}
              ref={fileInputRef}
              style={{ display: 'none' }}
            />
            <button style={styles.uploadButton} onClick={() => fileInputRef.current?.click()}>
              Attach Artifact (.evtx, .pcap, .log)...
            </button>

            {file && (
              <div style={styles.fileStatus}>
                <div style={styles.fileStatusRow}>
                  <span style={{ ...styles.fileBadge, backgroundColor: getFileBadge(file.name).color }}>
                    {getFileBadge(file.name).label}
                  </span>
                  <span style={styles.fileSize}>{(file.size / 1024).toFixed(1)} KB</span>
                </div>
                <div style={styles.fileName}>{file.name}</div>
              </div>
            )}

            <button
              style={{ ...styles.scanButton, opacity: file && !isScanning && isReady ? 1 : 0.6 }}
              onClick={runSOCTriage}
              disabled={!file || isScanning || !isReady}
            >
              {!isReady ? 'Engine Initializing...' : isScanning ? 'Triaging Forensic Stream...' : 'Run Incident Triage'}
            </button>

            {error && <div style={styles.errorText}>{error}</div>}
          </div>

          {/* ACTIVE DETECTION SIGNATURES */}
          <div style={styles.panel}>
            <div style={styles.panelTitle}>Detection Signatures</div>
            <div style={styles.profileDesc}>{selectedProfileMeta.description}</div>
            <ul style={styles.signatureList}>
              {selectedProfileMeta.rules.map((rule, idx) => (
                <li key={idx} style={styles.signatureItem}>
                  <span style={styles.bulletCheck}>›</span> {rule}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* RIGHT MAIN AREA: Report */}
        <div id="report-container" style={styles.mainArea}>
          <div className="no-print" style={styles.reportHeader}>
            <div style={styles.reportHeaderLeft}>
              <div style={styles.reportTitle}>Tier-1 SOC Incident Triage Report</div>
              <div style={styles.reportSubtitle}>
                Target: <span style={styles.targetThreatHighlight}>{selectedProfileMeta.label}</span>
              </div>
            </div>
            {report && (
              <div style={styles.buttonGroup}>
                <button style={styles.downloadButton} onClick={downloadReport}>
                  Export Report (.md)
                </button>
                <button style={styles.downloadButton} onClick={saveAsPDF}>
                  Save PDF
                </button>
              </div>
            )}
          </div>

          <div style={styles.reportContent}>
            {!report && !isScanning && (
              <div className="no-print" style={styles.placeholderState}>
                <div style={styles.placeholderIcon}>🛡️</div>
                <div style={styles.placeholderTitle}>Air-Gapped SOC Workbench Ready</div>
                <div style={styles.placeholderSub}>
                  Upload an EVTX event log, PCAP capture, or syslog artifact and execute deterministic triage against {selectedProfileMeta.label}.
                </div>
              </div>
            )}

            {isScanning && (
              <div className="no-print" style={styles.processingState}>
                <div style={styles.processingHeader}>
                  <div style={styles.loadingSpinner}></div>
                  <div>
                    <div style={styles.processingTitle}>SOC Engine Active — Analyzing Forensic Stream...</div>
                    <div style={styles.processingSub}>Ingesting {file?.name} & evaluating against {selectedProfileMeta.label} signatures</div>
                  </div>
                </div>
              </div>
            )}

            {report && (
              <div style={styles.renderedReport}>
                {renderReport(report)}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// --- CSS-in-JS STYLES ---
const styles: { [key: string]: React.CSSProperties } = {
  container: {
    display: 'flex',
    height: '100vh',
    backgroundColor: '#0F172A',
    color: '#E2E8F0',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    padding: '16px',
    boxSizing: 'border-box',
    gap: '16px'
  },
  sidebar: { width: '320px', display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto' },
  mainArea: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    border: '1px solid #1E293B',
    borderRadius: '8px',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.2)'
  },
  brandPanel: {
    backgroundColor: '#1E293B',
    border: '1px solid #334155',
    borderRadius: '8px',
    padding: '14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px'
  },
  brandRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  brandTitle: { fontSize: '1.25rem', fontWeight: 700, color: '#F8FAFC', letterSpacing: '-0.025em' },
  socBadge: { backgroundColor: '#3B82F6', color: '#FFFFFF', fontSize: '0.65rem', fontWeight: 700, padding: '2px 6px', borderRadius: '4px', letterSpacing: '0.05em' },
  subTitle: { fontSize: '0.75rem', color: '#94A3B8', marginBottom: '4px' },
  statusBadge: { display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', fontWeight: 600, padding: '4px 8px', borderRadius: '9999px', border: '1px solid', width: 'fit-content' },
  statusDot: { width: '6px', height: '6px', borderRadius: '50%' },
  progressBarContainer: { width: '100%', height: '5px', backgroundColor: '#334155', borderRadius: '3px', marginTop: '6px', overflow: 'hidden' },
  progressBar: { height: '100%', backgroundColor: '#10B981', transition: 'width 0.3s ease' },
  panel: { backgroundColor: '#1E293B', border: '1px solid #334155', borderRadius: '8px', padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px' },
  panelTitle: { fontSize: '0.8rem', fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.05em' },
  modelSelect: {
    width: '100%',
    padding: '8px 10px',
    backgroundColor: '#0F172A',
    color: '#F8FAFC',
    border: '1px solid #334155',
    borderRadius: '6px',
    fontSize: '0.8rem',
    outline: 'none',
    cursor: 'pointer',
    fontWeight: 500
  },
  modelSelectPlaceholder: {
    fontSize: '0.75rem',
    color: '#94A3B8',
    fontStyle: 'italic'
  },
  profileSelectGroup: { display: 'flex', flexDirection: 'column', gap: '6px' },
  activeProfileButton: { backgroundColor: '#3B82F6', color: '#FFFFFF', border: 'none', borderRadius: '6px', padding: '10px 12px', cursor: 'pointer', textAlign: 'left', fontWeight: 600, fontSize: '0.8rem' },
  inactiveProfileButton: { backgroundColor: '#0F172A', color: '#94A3B8', border: '1px solid #334155', borderRadius: '6px', padding: '10px 12px', cursor: 'pointer', textAlign: 'left', fontWeight: 500, fontSize: '0.8rem' },
  profileButtonHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  profileTag: { fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px', fontWeight: 700 },
  uploadButton: { backgroundColor: '#0F172A', color: '#E2E8F0', border: '1px dashed #475569', padding: '10px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500, fontSize: '0.8rem', borderRadius: '6px', textAlign: 'center' },
  fileStatus: { backgroundColor: '#0F172A', padding: '8px 10px', borderRadius: '6px', border: '1px solid #334155' },
  fileStatusRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' },
  fileBadge: { color: '#FFFFFF', fontSize: '0.65rem', fontWeight: 700, padding: '2px 6px', borderRadius: '4px' },
  fileSize: { fontSize: '0.7rem', color: '#64748B' },
  fileName: { fontFamily: '"SFMono-Regular", Consolas, monospace', color: '#F1F5F9', fontSize: '0.75rem', wordBreak: 'break-all' },
  scanButton: { backgroundColor: '#10B981', color: '#FFFFFF', border: 'none', padding: '10px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 700, fontSize: '0.85rem', borderRadius: '6px' },
  profileDesc: { fontSize: '0.75rem', color: '#94A3B8', lineHeight: '1.4' },
  signatureList: { margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '6px' },
  signatureItem: { fontSize: '0.75rem', color: '#CBD5E1', display: 'flex', alignItems: 'flex-start', gap: '6px', lineHeight: '1.3' },
  bulletCheck: { color: '#38BDF8', fontWeight: 700 },
  reportHeader: { backgroundColor: '#0F172A', borderBottom: '1px solid #1E293B', padding: '14px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  reportHeaderLeft: { display: 'flex', flexDirection: 'column', gap: '2px' },
  reportTitle: { fontSize: '1.1rem', fontWeight: 700, color: '#F8FAFC' },
  reportSubtitle: { fontSize: '0.75rem', color: '#94A3B8' },
  targetThreatHighlight: { color: '#38BDF8', fontWeight: 600 },
  buttonGroup: { display: 'flex', gap: '8px' },
  downloadButton: { backgroundColor: '#1E293B', color: '#F8FAFC', border: '1px solid #334155', padding: '6px 14px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600, fontSize: '0.75rem', borderRadius: '4px' },
  reportContent: { flex: 1, padding: '32px 48px', overflowY: 'auto', backgroundColor: '#FFFFFF', color: '#0F172A' },
  placeholderState: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748B' },
  placeholderIcon: { fontSize: '40px', marginBottom: '16px' },
  placeholderTitle: { fontSize: '1.2rem', fontWeight: 700, color: '#0F172A', marginBottom: '6px' },
  placeholderSub: { fontSize: '0.85rem', maxWidth: '440px', textAlign: 'center', lineHeight: '1.5' },
  processingState: { display: 'flex', flexDirection: 'column', width: '100%', maxWidth: '600px', margin: '40px auto' },
  processingHeader: { display: 'flex', alignItems: 'center', gap: '14px', backgroundColor: '#F8FAFC', padding: '16px', borderRadius: '8px', border: '1px solid #E2E8F0' },
  loadingSpinner: { width: '24px', height: '24px', border: '3px solid #E2E8F0', borderTop: '3px solid #0F172A', borderRadius: '50%', animation: 'spin 1s linear infinite' },
  processingTitle: { fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' },
  processingSub: { fontSize: '0.75rem', color: '#64748B' },
  errorText: { color: '#EF4444', fontSize: '0.75rem', marginTop: '4px', backgroundColor: '#FEF2F2', padding: '8px', borderRadius: '4px', border: '1px solid #F87171' },
  renderedReport: { lineHeight: '1.6', color: '#334155', fontSize: '0.95rem' },
  h1: { color: '#0F172A', fontSize: '1.4rem', fontWeight: 800, borderBottom: '2px solid #E2E8F0', paddingBottom: '8px', marginBottom: '20px', marginTop: 0 },
  h2: { color: '#0F172A', fontSize: '1.1rem', fontWeight: 700, marginTop: '28px', marginBottom: '10px', borderBottom: '1px solid #F1F5F9', paddingBottom: '4px' },
  h3: { color: '#1E293B', fontSize: '0.95rem', fontWeight: 600, marginTop: '18px', marginBottom: '8px' },
  listItem: { marginBottom: '10px', marginLeft: '18px', lineHeight: '1.5' },
  citationBadge: { display: 'inline-block', backgroundColor: '#F0FDF4', color: '#166534', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600, border: '1px solid #BBF7D0', marginLeft: '6px', marginRight: '6px', fontFamily: '"SFMono-Regular", Consolas, monospace' },
  badge: { display: 'inline-block', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 700, border: '1px solid', marginRight: '8px' },
  text: { marginBottom: '10px' },
  tableWrapper: { margin: '14px 0', overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', border: '1px solid #E2E8F0' },
  th: { backgroundColor: '#F8FAFC', color: '#0F172A', fontWeight: 700, padding: '8px 12px', border: '1px solid #E2E8F0', textAlign: 'left' },
  td: { padding: '8px 12px', border: '1px solid #E2E8F0', color: '#334155' },
  trEven: { backgroundColor: '#FFFFFF' },
  trOdd: { backgroundColor: '#F8FAFC' }
};