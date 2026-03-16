import { useEffect, useState } from "react";
import { getConfig, updateConfig } from "../lib/config";
import { apiFetch } from "../lib/api";

interface RuntimeSettingsPayload {
  detection_confidence: number;
  plate_confidence: number;
  face_threshold: number;
}

export function SettingsView() {
  const initialConfig = getConfig();
  const [apiUrl, setApiUrl] = useState(initialConfig.API_URL);
  const [apiKey, setApiKey] = useState(initialConfig.API_KEY);
  const [showKey, setShowKey] = useState(false);
  const [connStatus, setConnStatus] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [healthData, setHealthData] = useState<any>(null);
  const [detectThresh, setDetectThresh] = useState(0.30);
  const [plateThresh, setPlateThresh] = useState(0.25);
  const [faceThresh, setFaceThresh] = useState(1.05);
  const [savingRuntime, setSavingRuntime] = useState(false);
  const [savingConnection, setSavingConnection] = useState(false);

  const loadRuntimeSettings = async () => {
    try {
      const payload = await apiFetch<RuntimeSettingsPayload>("/api/settings/runtime");
      if (typeof payload?.detection_confidence === "number") setDetectThresh(payload.detection_confidence);
      if (typeof payload?.plate_confidence === "number") setPlateThresh(payload.plate_confidence);
      if (typeof payload?.face_threshold === "number") setFaceThresh(payload.face_threshold);
    } catch {
      // Ignore when the backend is offline.
    }
  };

  const testConnection = async () => {
    setConnStatus("testing");
    try {
      const [health, stats] = await Promise.all([
        apiFetch("/api/health") as Promise<any>,
        apiFetch("/api/system/stats") as Promise<any>,
      ]);
      setHealthData({ ...health, ...stats });
      setConnStatus("ok");
    } catch {
      setConnStatus("fail");
      setHealthData(null);
    }
  };

  useEffect(() => {
    testConnection();
    loadRuntimeSettings();
  }, []);

  const saveConnection = async () => {
    setSavingConnection(true);
    updateConfig({ API_URL: apiUrl, API_KEY: apiKey });
    await testConnection();
    setSavingConnection(false);
  };

  const applyRuntimeSettings = async () => {
    setSavingRuntime(true);
    try {
      await apiFetch("/api/settings/runtime", {
        method: "POST",
        body: JSON.stringify({
          detection_confidence: detectThresh,
          plate_confidence: plateThresh,
          face_threshold: faceThresh,
        }),
      });
      await loadRuntimeSettings();
    } catch {
      // Ignore and let the operator retry.
    } finally {
      setSavingRuntime(false);
    }
  };

  const clearAllEvents = async () => {
    if (!confirm("Clear all stored event logs?")) return;
    try {
      await apiFetch("/api/admin/events/clear", { method: "POST" });
      await testConnection();
    } catch {
      // Ignore here; connection banner already covers backend failures.
    }
  };

  const removeAllCameras = async () => {
    if (!confirm("Remove all active cameras?")) return;
    try {
      await apiFetch("/api/admin/cameras/remove-all", { method: "POST" });
      window.dispatchEvent(new CustomEvent("cameras-updated"));
      await testConnection();
    } catch {
      // Ignore here; connection banner already covers backend failures.
    }
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
            <input
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              className="w-full font-mono text-[11px] bg-background border border-border px-3 py-1.5 text-foreground"
            />
          </Field>
          <Field label="API Key">
            <div className="flex gap-2">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="flex-1 font-mono text-[11px] bg-background border border-border px-3 py-1.5 text-foreground"
              />
              <button
                onClick={() => setShowKey((prev) => !prev)}
                className="px-2 border border-border text-[9px] font-mono text-muted-foreground hover:text-foreground transition-all"
              >
                {showKey ? "HIDE" : "SHOW"}
              </button>
            </div>
          </Field>
          <div className="flex gap-2">
            <button
              onClick={saveConnection}
              disabled={savingConnection}
              className="px-4 py-1.5 border border-primary/50 bg-primary/10 text-[9px] font-mono uppercase text-primary hover:bg-primary/20 transition-all disabled:opacity-50"
            >
              {savingConnection ? "APPLYING..." : "APPLY CONNECTION"}
            </button>
            <button
              onClick={testConnection}
              className="px-4 py-1.5 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:border-primary/50 hover:text-foreground transition-all"
            >
              TEST CONNECTION
            </button>
          </div>
          <div className="mt-2 text-[9px] font-mono">
            {connStatus === "testing" && <span className="text-muted-foreground">TESTING...</span>}
            {connStatus === "ok" && (
              <span className="text-status-online">● CONNECTED // {healthData?.device || "SERVER"}</span>
            )}
            {connStatus === "fail" && <span className="text-status-alert">● CONNECTION FAILED</span>}
          </div>
        </Section>

        <Section title="DETECTION THRESHOLDS">
          {[
            {
              label: "DETECTION CONFIDENCE",
              val: detectThresh,
              set: setDetectThresh,
              min: 0.10,
              max: 0.80,
              step: 0.05,
            },
            {
              label: "PLATE DETECTOR CONFIDENCE",
              val: plateThresh,
              set: setPlateThresh,
              min: 0.10,
              max: 0.80,
              step: 0.05,
            },
          ].map(({ label, val, set, min, max, step }) => (
            <Field key={label} label={label}>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={min}
                  max={max}
                  step={step}
                  value={val}
                  onChange={(e) => set(parseFloat(e.target.value))}
                  className="flex-1"
                  style={{ accentColor: "hsl(var(--primary))" }}
                />
                <span className="text-[10px] font-mono text-primary w-10 text-right">{val.toFixed(2)}</span>
              </div>
            </Field>
          ))}
          <Field label="FACE MATCH THRESHOLD">
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0.70}
                max={1.30}
                step={0.05}
                value={faceThresh}
                onChange={(e) => setFaceThresh(parseFloat(e.target.value))}
                className="flex-1"
                style={{ accentColor: "hsl(var(--primary))" }}
              />
              <span className="text-[10px] font-mono text-primary w-10 text-right">{faceThresh.toFixed(2)}</span>
            </div>
            <div className="text-[8px] font-mono text-muted-foreground mt-0.5">Lower = stricter. Higher = more lenient.</div>
          </Field>
          <button
            onClick={applyRuntimeSettings}
            disabled={savingRuntime}
            className="px-4 py-1.5 border border-primary/50 bg-primary/10 text-[9px] font-mono uppercase text-primary hover:bg-primary/20 transition-all disabled:opacity-50"
          >
            {savingRuntime ? "SAVING..." : "APPLY RUNTIME SETTINGS"}
          </button>
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
                ["Admin Auth", healthData.admin_auth_enabled ? "ENABLED" : "DISABLED"],
                ["Active Cameras", healthData.active_cameras ?? "--"],
                ["Watchlist Subjects", healthData.watchlist_count ?? "--"],
                ["CPU Count", healthData.cpu_count ?? "--"],
                ["RAM Used", healthData.ram_used_gb ? `${healthData.ram_used_gb} GB` : "--"],
                ["CPU Load", healthData.cpu_percent ? `${healthData.cpu_percent.toFixed(1)}%` : "--"],
                ["GPU Load", healthData.gpu_available ? `${(healthData.gpu_percent || 0).toFixed(1)}%` : "N/A"],
              ].map(([k, v]) => (
                <div key={k} className="flex border-b border-border/50 last:border-0">
                  <div className="w-48 px-3 py-1.5 text-[9px] font-mono text-muted-foreground uppercase border-r border-border/50">{k}</div>
                  <div className="flex-1 px-3 py-1.5 text-[9px] font-mono text-foreground">{v}</div>
                </div>
              ))}
            </div>
            <button
              onClick={testConnection}
              className="mt-2 px-3 py-1 border border-border text-[9px] font-mono text-muted-foreground hover:text-foreground uppercase transition-all"
            >
              REFRESH
            </button>
          </Section>
        )}

        <Section title="DANGER ZONE">
          <div className="border-l-2 border-status-alert pl-3 space-y-2">
            <button
              onClick={clearAllEvents}
              className="px-4 py-1.5 border border-status-alert/40 bg-status-alert/10 text-status-alert text-[9px] font-mono uppercase hover:bg-status-alert/20 transition-all block"
            >
              CLEAR ALL EVENTS
            </button>
            <button
              onClick={removeAllCameras}
              className="px-4 py-1.5 border border-status-alert/40 bg-status-alert/10 text-status-alert text-[9px] font-mono uppercase hover:bg-status-alert/20 transition-all block"
            >
              REMOVE ALL CAMERAS
            </button>
          </div>
        </Section>
      </div>
    </div>
  );
}
