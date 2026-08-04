import React, { useState, useRef, useEffect } from 'react';
import { save } from '@tauri-apps/plugin-dialog';
import { writeTextFile } from '@tauri-apps/plugin-fs';

export default function App() {
  // --- ENGINE INITIALIZATION STATES ---
  const [modelStatus, setModelStatus] = useState<string>("Checking AI engine...");
  const [downloadProgress, setDownloadProgress] = useState<number>(0);
  const [isReady, setIsReady] = useState<boolean>(false);

  // --- APP STATES ---
  const [file, setFile] = useState<File | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scanSteps, setScanSteps] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // --- EFFECT: INITIALIZE ENGINE ---
  useEffect(() => {
    const initializeEngine = async () => {
      try {
        // 1. Check if the model already exists
        const tagsResponse = await fetch("http://127.0.0.1:11434/api/tags");
        const tagsData = await tagsResponse.json();
        const hasModel = tagsData.models?.some((m: any) => m.name === "granite4.1:8b");

        if (hasModel) {
          setModelStatus("Air-Gapped Engine Ready");
          setIsReady(true);
          return;
        }

        // 2. If missing, trigger the download via Ollama's REST API
        setModelStatus("Downloading Granite 4.1 Model (First Boot Only)...");
        
        const pullResponse = await fetch("http://127.0.0.1:11434/api/pull", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: "granite4.1:8b" })
        });

        // 3. Read the streaming response to update the progress bar
        const reader = pullResponse.body?.getReader();
        if (!reader) return;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = new TextDecoder().decode(value);
          const lines = chunk.split("\n").filter(Boolean);
          
          for (const line of lines) {
            const json = JSON.parse(line);
            if (json.total && json.completed) {
              const percentage = Math.round((json.completed / json.total) * 100);
              setDownloadProgress(percentage);
            }
          }
        }

        setModelStatus("Air-Gapped Engine Ready");
        setIsReady(true);

      } catch (err) {
        setModelStatus("Engine initialization failed. Retrying...");
      }
    };

    initializeEngine();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setReport(null);
      setError(null);
      setScanSteps([]);
    }
  };

  // NATIVE TAURI SAVE (MARKDOWN)
  const downloadReport = async () => {
    if (!report) return;
    try {
      const suggestedName = `${file?.name.replace(/\.[^/.]+$/, "") || 'Audit'}_Red_Flag_Report.md`;
      const filePath = await save({
        filters: [{ name: 'Markdown', extensions: ['md'] }],
        defaultPath: suggestedName,
      });

      if (filePath) {
        await writeTextFile(filePath, report);
      }
    } catch (err: any) {
      setError(`Failed to save file: ${err.message || err}`);
    }
  };

  // NATIVE BROWSER PRINT ENGINE (PDF)
  const saveAsPDF = () => {
    window.print();
  };

  // --- EFFECT: SCANNING ANIMATION ---
  useEffect(() => {
    if (isScanning) {
      setScanSteps(["[SYSTEM] Initializing air-gapped environment..."]);
      
      const timers = [
        setTimeout(() => setScanSteps(prev => [...prev, "[INGEST] Extracting raw text layers from PDF..."]), 1500),
        setTimeout(() => setScanSteps(prev => [...prev, "[ENGINE] Allocating local memory for model execution..."]), 3500),
        setTimeout(() => setScanSteps(prev => [...prev, "[SCAN] Cross-referencing Change of Control triggers..."]), 6500),
        setTimeout(() => setScanSteps(prev => [...prev, "[SCAN] Evaluating termination penalties & notice periods..."]), 11000),
        setTimeout(() => setScanSteps(prev => [...prev, "[SCAN] Synthesizing narrative risk factors (CIM)..."]), 16000),
        setTimeout(() => setScanSteps(prev => [...prev, "[ENGINE] Awaiting final JSON payload from local model..."]), 22000),
      ];

      return () => timers.forEach(clearTimeout);
    } else {
      setScanSteps([]);
    }
  }, [isScanning]);

  const runDeterministicScan = async () => {
    if (!file) {
      setError("Please upload a target document first.");
      return;
    }

    setIsScanning(true);
    setError(null);
    setReport(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/ma/parse", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      const data = await response.json();
      setReport(data.report_markdown);
    } catch (err: any) {
      setError(err.message || "Failed to connect to the offline engine.");
    } finally {
      setIsScanning(false);
    }
  };

  const renderReport = (text: string) => {
    const lines = text.split('\n');
    return lines.map((line, index) => {
      if (line.startsWith('# ')) {
        return <h2 key={index} style={styles.h1}>{line.replace('# ', '')}</h2>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={index} style={styles.h2}>{line.replace('## ', '')}</h3>;
      }
      if (line.startsWith('* ') || line.startsWith('- ')) {
        let content = line.substring(2);
        const citationMatch = content.match(/Citation:\s*(.*)/i) || content.match(/\[(.*?)\]/);
        
        if (citationMatch) {
          const splitText = content.split(citationMatch[0]);
          return (
            <li key={index} style={styles.listItem}>
              <span dangerouslySetInnerHTML={{ __html: splitText[0].replace(/\*\*(.*?)\*\*/g, '<strong style="color: #111827; font-weight: 600;">$1</strong>') }} />
              <span style={styles.citationBadge}>{citationMatch[0]}</span>
              {splitText[1]}
            </li>
          );
        }

        return (
          <li key={index} style={styles.listItem} dangerouslySetInnerHTML={{ __html: content.replace(/\*\*(.*?)\*\*/g, '<strong style="color: #111827; font-weight: 600;">$1</strong>') }} />
        );
      }
      if (line.trim() === '') {
        return <br key={index} />;
      }
      return <p key={index} style={styles.text}>{line}</p>;
    });
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
            <div style={styles.brandTitle}>Vault AI</div>
            
            {/* DYNAMIC STATUS BADGE */}
            <div style={{...styles.statusBadge, backgroundColor: isReady ? '#D1FAE5' : '#FEF3C7', borderColor: isReady ? '#34D399' : '#FBBF24', color: isReady ? '#047857' : '#B45309'}}>
              <span style={{...styles.statusDot, backgroundColor: isReady ? '#059669' : '#D97706'}}></span>
              {modelStatus}
            </div>
            
            {/* DOWNLOAD PROGRESS BAR */}
            {downloadProgress > 0 && !isReady && (
              <div style={styles.progressBarContainer}>
                <div style={{...styles.progressBar, width: `${downloadProgress}%`}}></div>
              </div>
            )}
          </div>

          <div style={styles.panel}>
            <div style={styles.panelTitle}>Target Document</div>
            <input 
              type="file" 
              accept="application/pdf" 
              onChange={handleFileChange} 
              ref={fileInputRef}
              style={{ display: 'none' }} 
            />
            <button style={styles.uploadButton} onClick={() => fileInputRef.current?.click()}>
              Browse Files...
            </button>
            
            {file && (
              <div style={styles.fileStatus}>
                Attached: <span style={styles.fileName}>{file.name}</span>
              </div>
            )}

            <button 
              style={{...styles.scanButton, opacity: file && !isScanning && isReady ? 1 : 0.6}} 
              onClick={runDeterministicScan}
              disabled={!file || isScanning || !isReady}
            >
              {!isReady ? 'Engine Not Ready' : isScanning ? 'Processing...' : 'Run Analysis'}
            </button>
            
            {error && <div style={styles.errorText}>{error}</div>}
          </div>

          <div style={styles.panel}>
            <div style={styles.panelTitle}>Active Scan Profile</div>
            <div style={styles.profileText}>M&A Red Flag Extraction</div>
            <ul style={styles.profileList}>
              <li>Change of Control</li>
              <li>Termination & Notice</li>
              <li>Assignability Restrictions</li>
              <li>Customer Concentration</li>
              <li>Management Turnover</li>
              <li>Regulatory Liabilities</li>
            </ul>
          </div>
        </div>

        {/* RIGHT MAIN AREA: Report */}
        <div id="report-container" style={styles.mainArea}>
          <div className="no-print" style={styles.reportHeader}>
            <div style={styles.reportTitle}>Red Flag Audit Report</div>
            {report && (
              <div style={styles.buttonGroup}>
                <button style={styles.downloadButton} onClick={downloadReport}>
                  Save (.md)
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
                <div style={styles.placeholderIcon}>📄</div>
                <div style={styles.placeholderTitle}>Ready for Analysis</div>
                <div style={styles.placeholderSub}>Upload a document and run the analysis to generate a red flag report.</div>
              </div>
            )}
            
            {isScanning && (
              <div className="no-print" style={styles.processingState}>
                <div style={styles.processingHeader}>
                  <div style={styles.loadingSpinner}></div>
                  <span style={styles.processingTitle}>Engine Active</span>
                </div>
                <div style={styles.logTerminal}>
                  {scanSteps.map((step, idx) => (
                    <div key={idx} style={styles.logLine}>
                      <span style={styles.timestamp}>{new Date().toLocaleTimeString()}</span> {step}
                    </div>
                  ))}
                  <div style={styles.blinkingCursor}>_</div>
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
    backgroundColor: '#F3F4F6',
    color: '#374151',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    padding: '16px',
    boxSizing: 'border-box',
    gap: '16px'
  },
  sidebar: { width: '300px', display: 'flex', flexDirection: 'column', gap: '16px' },
  mainArea: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    border: '1px solid #E5E7EB',
    borderRadius: '8px',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
  },
  brandPanel: { padding: '4px 8px' },
  brandTitle: { fontSize: '1.25rem', fontWeight: 700, color: '#111827', letterSpacing: '-0.025em', marginBottom: '8px' },
  statusBadge: { display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', fontWeight: 600, padding: '4px 8px', borderRadius: '9999px', border: '1px solid' },
  statusDot: { width: '6px', height: '6px', borderRadius: '50%' },
  progressBarContainer: { width: '100%', height: '6px', backgroundColor: '#E5E7EB', borderRadius: '3px', marginTop: '12px', overflow: 'hidden' },
  progressBar: { height: '100%', backgroundColor: '#059669', transition: 'width 0.3s ease' },
  panel: { backgroundColor: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: '8px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' },
  panelTitle: { fontSize: '0.875rem', fontWeight: 600, color: '#111827', borderBottom: '1px solid #F3F4F6', paddingBottom: '8px' },
  uploadButton: { backgroundColor: '#FFFFFF', color: '#374151', border: '1px dashed #D1D5DB', padding: '12px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500, fontSize: '0.875rem', borderRadius: '6px' },
  fileStatus: { fontSize: '0.8rem', color: '#6B7280', backgroundColor: '#F9FAFB', padding: '8px', borderRadius: '4px', border: '1px solid #F3F4F6' },
  fileName: { fontFamily: '"SFMono-Regular", Consolas, monospace', color: '#111827', fontWeight: 500 },
  scanButton: { backgroundColor: '#0F172A', color: '#FFFFFF', border: 'none', padding: '10px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600, fontSize: '0.875rem', borderRadius: '6px', marginTop: '4px' },
  profileText: { fontSize: '0.85rem', fontWeight: 500, color: '#4B5563' },
  profileList: { margin: 0, paddingLeft: '16px', fontSize: '0.8rem', color: '#6B7280', lineHeight: '1.6' },
  reportHeader: { backgroundColor: '#F9FAFB', borderBottom: '1px solid #E5E7EB', padding: '12px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  reportTitle: { fontSize: '1rem', fontWeight: 600, color: '#111827' },
  buttonGroup: { display: 'flex', gap: '8px' },
  downloadButton: { backgroundColor: '#FFFFFF', color: '#374151', border: '1px solid #D1D5DB', padding: '6px 16px', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600, fontSize: '0.75rem', borderRadius: '4px', transition: 'all 0.2s ease', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' },
  reportContent: { flex: 1, padding: '32px 48px', overflowY: 'auto' },
  placeholderState: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6B7280' },
  placeholderIcon: { fontSize: '32px', marginBottom: '16px', opacity: 0.5 },
  placeholderTitle: { fontSize: '1.1rem', fontWeight: 600, color: '#374151', marginBottom: '4px' },
  placeholderSub: { fontSize: '0.875rem' },
  processingState: { display: 'flex', flexDirection: 'column', width: '100%', maxWidth: '600px', margin: '0 auto', marginTop: '40px' },
  processingHeader: { display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' },
  loadingSpinner: { width: '20px', height: '20px', border: '2px solid #E5E7EB', borderTop: '2px solid #0F172A', borderRadius: '50%', animation: 'spin 1s linear infinite' },
  processingTitle: { fontSize: '1rem', fontWeight: 600, color: '#111827' },
  logTerminal: { backgroundColor: '#111827', borderRadius: '6px', padding: '16px', fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Courier, monospace', fontSize: '0.85rem', color: '#A7F3D0', minHeight: '200px', boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.2)' },
  logLine: { marginBottom: '8px', lineHeight: '1.4' },
  timestamp: { color: '#6B7280', marginRight: '8px' },
  blinkingCursor: { display: 'inline-block', animation: 'blink 1s step-end infinite', color: '#A7F3D0' },
  errorText: { color: '#DC2626', fontSize: '0.8rem', marginTop: '4px', backgroundColor: '#FEF2F2', padding: '8px', borderRadius: '4px', border: '1px solid #FCA5A5' },
  renderedReport: { lineHeight: '1.6', color: '#374151', fontSize: '0.95rem' },
  h1: { color: '#111827', fontSize: '1.5rem', fontWeight: 700, borderBottom: '2px solid #E5E7EB', paddingBottom: '8px', marginBottom: '24px', marginTop: 0 },
  h2: { color: '#111827', fontSize: '1.1rem', fontWeight: 600, marginTop: '32px', marginBottom: '12px' },
  listItem: { marginBottom: '12px', marginLeft: '20px', paddingLeft: '4px' },
  citationBadge: { display: 'inline-block', backgroundColor: '#EFF6FF', color: '#1D4ED8', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600, border: '1px solid #BFDBFE', marginLeft: '6px', marginRight: '6px', fontFamily: '"SFMono-Regular", Consolas, monospace', verticalAlign: 'baseline' },
  text: { marginBottom: '12px' }
};