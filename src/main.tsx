import React, { Component, ErrorInfo, ReactNode } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("SOC Workbench Uncaught Error:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 32, background: "#0F172A", color: "#F8FAFC", height: "100vh" }}>
          <h2 style={{ color: "#EF4444", marginTop: 0 }}>SOC Workbench Error</h2>
          <p style={{ color: "#94A3B8" }}>An error occurred while rendering the workbench interface:</p>
          <pre style={{ background: "#1E293B", padding: 16, borderRadius: 8, color: "#FCA5A5", overflowX: "auto" }}>
            {this.state.error?.stack || this.state.error?.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{ padding: "8px 16px", background: "#3B82F6", color: "#FFF", border: "none", borderRadius: 4, cursor: "pointer", fontWeight: 600 }}
          >
            Reload Workbench
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
