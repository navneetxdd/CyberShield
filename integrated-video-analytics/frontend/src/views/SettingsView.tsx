import { useState, useEffect } from "react";
import { CONFIG } from "../lib/config";
import { apiFetch } from "../lib/api";

export function SettingsView() {
  const [apiUrl, setApiUrl] = useState(CONFIG.API_URL);
  const [apiKey, setApiKey] = useState(CONFIG.API_KEY);
  const [showKey, setShowKey] = useState(false);
  const [connStatus, setConnStatus] = useState<"idle"|"testing"|"ok"|"fail">("idle");
  const [healthData, setHealthData] = useState<any>(null);
  const [detectThresh, setDetectThresh] = useState(0.30);
  const [plateThresh, setPlateThresh] = useState(0.25);
  const [faceThresh, setFaceThresh] = useState(1.05);

  const testConnection = async () => {
    setConnStatus("testing");
    try {
      const data = await apiFetch("/api/health") as any;
      setHealthData(data);
      setConnStatus("ok");
    } catch {
      setConnStatus("fail");
      setHealthData(null);
    }
  };

  useEffect(() => {
    testConnection();
    apiFetch<{ value: number }>("/api/settings/face-threshold")
      .then((data) => {
        if (typeof data?.value === "number") {
          setFaceThresh(data.value);
        }
      })
      .catch(() => {
        // Keep default when the settings endpoint is unavailable.
      });
  }, []);

  const applyFaceThreshold = async (val: number) => {
    setFaceThresh(val);
    try { await apiFetch("/api/settings/face-threshold", { method: "POST", body: JSON.stringify({ value: val }) }); } catch { /**/ }
  };

  const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div className="border-t border-border pt-4">
      <div className="text-[10px] font-mono text-primary uppercase tracking-widest mb-3">{title}</div>
      {children}
    </div>
  );

  const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div className="flex items-center justify-between mb-2">
      <span className="text-[9px] font-mono text-muted-foreground uppercase w-48">{label}</span>
      <div className="flex-1">{children}</div>
    </div>
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[700px] mx-auto p-8 space-y-4">
        <div className="text-[12px] font-mono text-primary uppercase tracking-widest border-b border-border pb-2">
          SYSTEM SETTINGS
        </div>

        <Section title="CONNECTION">
          <Field label="Backend URL">
            <input value={apiUrl} onChange={e => setApiUrl(e.target.value)}
              className="w-full font-mono text-[11px] bg-background border border-border px-3 py-1.5 text-foreground" />
          </Field>
          <Field label="API Key">
            <div className="flex gap-2">
              <input type={showKey ? "text" : "password"} value={apiKey} onChange={e => setApiKey(e.target.value)}
                className="flex-1 font-mono text-[11px] bg-background border border-border px-3 py-1.5 text-foreground" />
              <button onClick={() => setShowKey(p=>!p)} className="px-2 border border-border text-[9px] font-mono text-muted-foreground hover:text-foreground transition-all">
                {showKey ? "HIDE" : "SHOW"}
              </button>
            </div>
          </Field>
          <button onClick={testConnection}
            className="px-4 py-1.5 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:border-primary/50 hover:text-foreground transition-all">
            TEST CONNECTION
          </button>
          <div className="mt-2 text-[9px] font-mono">
            {connStatus === "testing" && <span className="text-muted-foreground">TESTING...</span>}
            {connStatus === "ok" && (
              <span className="text-status-online">
                ● CONNECTED // CyberShield {healthData?.device || "SERVER"}
              </span>
            )}
            {connStatus === "fail" && <span className="text-status-alert">● CONNECTION FAILED // Check backend at port 8080</span>}
          </div>
        </Section>

        <Section title="DETECTION THRESHOLDS">
          {[
            { label: "DETECTION CONFIDENCE", val: detectThresh, set: setDetectThresh, min: 0.20, max: 0.80, step: 0.05 },
            { label: "PLATE CONFIDENCE", val: plateThresh, set: setPlateThresh, min: 0.15, max: 0.70, step: 0.05 },
          ].map(({ label, val, set, min, max, step }) => (
            <Field key={label} label={label}>
              <div className="flex items-center gap-3">
                <input type="range" min={min} max={max} step={step} value={val}
                  onChange={e => set(parseFloat(e.target.value))}
                  className="flex-1" style={{ accentColor: "hsl(var(--primary))" }} />
                <span className="text-[10px] font-mono text-primary w-10 text-right">{val.toFixed(2)}</span>
              </div>
            </Field>
          ))}
          <Field label="FACE MATCH THRESHOLD">
            <div className="flex items-center gap-3">
              <input type="range" min={0.70} max={1.30} step={0.05} value={faceThresh}
                onChange={e => applyFaceThreshold(parseFloat(e.target.value))}
                className="flex-1" style={{ accentColor: "hsl(var(--primary))" }} />
              <span className="text-[10px] font-mono text-primary w-10 text-right">{faceThresh.toFixed(2)}</span>
            </div>
            <div className="text-[8px] font-mono text-muted-foreground mt-0.5">Lower = stricter. Higher = more lenient.</div>
          </Field>
        </Section>

        <Section title="PRIVACY">
          <div className="flex items-center justify-between border border-border/40 px-3 py-2 bg-border/10">
            <div>
              <div className="text-[10px] font-mono text-muted-foreground">FACE BLUR ENABLED</div>
              <div className="text-[9px] font-mono text-muted-foreground/60">Required for compliance</div>
            </div>
            <div className="text-[9px] font-mono text-muted-foreground">ALWAYS ON</div>
          </div>
          <div className="mt-2 text-[9px] font-mono text-muted-foreground/60 leading-relaxed">
            Non-watchlist faces are anonymized before display. Only confirmed watchlist matches are shown unblurred.
          </div>
        </Section>

        {healthData && (
          <Section title="SYSTEM INFORMATION">
            <div className="border border-border">
              {[
                ["Device", healthData.device || "--"],
                ["Active Cameras", healthData.active_cameras ?? "--"],
                ["Watchlist Subjects", healthData.watchlist_count ?? "--"],
                ["CPU Count", healthData.cpu_count ?? "--"],
                ["RAM Used", healthData.ram_used_gb ? `${healthData.ram_used_gb} GB` : "--"],
              ].map(([k, v]) => (
                <div key={k} className="flex border-b border-border/50 last:border-0">
                  <div className="w-48 px-3 py-1.5 text-[9px] font-mono text-muted-foreground uppercase border-r border-border/50">{k}</div>
                  <div className="flex-1 px-3 py-1.5 text-[9px] font-mono text-foreground">{v}</div>
                </div>
              ))}
            </div>
            <button onClick={testConnection} className="mt-2 px-3 py-1 border border-border text-[9px] font-mono text-muted-foreground hover:text-foreground uppercase transition-all">
              REFRESH
            </button>
          </Section>
        )}

        <Section title="DANGER ZONE">
          <div className="border-l-2 border-status-alert pl-3 space-y-2">
            <button onClick={() => alert("Clear events: not implemented in this demo.")}
              className="px-4 py-1.5 border border-status-alert/40 bg-status-alert/10 text-status-alert text-[9px] font-mono uppercase hover:bg-status-alert/20 transition-all block">
              CLEAR ALL EVENTS
            </button>
            <button onClick={() => alert("Remove cameras: stop all streams from backend.")}
              className="px-4 py-1.5 border border-status-alert/40 bg-status-alert/10 text-status-alert text-[9px] font-mono uppercase hover:bg-status-alert/20 transition-all block">
              REMOVE ALL CAMERAS
            </button>
          </div>
        </Section>
      </div>
    </div>
  );
}
