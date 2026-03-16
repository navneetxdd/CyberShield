import { useState, useCallback, useMemo, useRef } from "react";
import { Plus, Pause, Camera as CameraIcon, Trash2, LayoutGrid, Maximize2, Play, X, Upload, CheckCircle2 } from "lucide-react";
import { CONFIG } from "@/lib/config";
import { CyberShieldState } from "@/pages/Index";
import { CameraGrid } from "@/components/live/CameraGrid";
import { VideoPlayer } from "@/components/VideoPlayer";
import { IntelligenceHub } from "@/components/IntelligenceHub";
import { MetricsRow } from "@/components/MetricsRow";
import { apiFetch } from "@/lib/api";

interface LiveViewProps {
  cameras: string[];
  activeCamera: string;
  state: CyberShieldState;
  onSwitchCamera: (id: string) => void;
  onAddFeed: () => void;
  onFaceClick?: (face: any) => void;
  onPlateClick?: (plate: any) => void;
  videoFlash?: boolean;
}

const DEFAULT_DELAYS = [0, 15, 30];
const DEFAULT_CAMERA_IDS = ["camera_1", "camera_2", "camera_3"];

interface DemoEntry {
  camera_id: string;
  file: File | null;
  stagedPath: string;     // server path after staging
  delay_seconds: number;
  uploadProgress: number; // 0-100
  uploadDone: boolean;
  uploadError: string;
}

function DemoSequenceModal({ onClose, onLaunched }: { onClose: () => void; onLaunched: () => void }) {
  const [entries, setEntries] = useState<DemoEntry[]>(() =>
    DEFAULT_CAMERA_IDS.map((id, i) => ({
      camera_id: id,
      file: null,
      stagedPath: "",
      delay_seconds: DEFAULT_DELAYS[i],
      uploadProgress: 0,
      uploadDone: false,
      uploadError: "",
    }))
  );
  const [status, setStatus] = useState<"idle" | "uploading" | "launching" | "done">("idle");
  const [error, setError] = useState("");
  const fileRefs = [
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
  ];

  const updateEntry = (i: number, patch: Partial<DemoEntry>) =>
    setEntries(prev => prev.map((e, idx) => idx === i ? { ...e, ...patch } : e));

  const handleFileSelect = (i: number, f: File) => {
    updateEntry(i, { file: f, stagedPath: "", uploadDone: false, uploadProgress: 0, uploadError: "" });
  };

  const stageFile = (entry: DemoEntry, i: number): Promise<string> =>
    new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append("file", entry.file!);
      formData.append("camera_id", entry.camera_id);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${CONFIG.API_URL}/api/video/stage`);
      xhr.setRequestHeader("X-API-Key", CONFIG.API_KEY);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          updateEntry(i, { uploadProgress: Math.round((e.loaded / e.total) * 100) });
        }
      };
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (data?.status === "success" && data.path) {
            updateEntry(i, { uploadDone: true, uploadProgress: 100, stagedPath: data.path });
            resolve(data.path);
          } else {
            const msg = data?.detail || "Upload failed";
            updateEntry(i, { uploadError: msg });
            reject(new Error(msg));
          }
        } catch {
          updateEntry(i, { uploadError: "Invalid server response" });
          reject(new Error("Invalid server response"));
        }
      };
      xhr.onerror = () => {
        updateEntry(i, { uploadError: "Network error" });
        reject(new Error("Network error"));
      };
      xhr.send(formData);
    });

  const launch = async () => {
    const active = entries.filter(e => e.file);
    if (!active.length) { setError("Add at least one video file."); return; }
    setError("");
    setStatus("uploading");

    try {
      // Stage all files in parallel
      const paths = await Promise.all(
        entries.map((e, i) => e.file ? stageFile(e, i) : Promise.resolve(""))
      );

      setStatus("launching");
      const payload = entries
        .map((e, i) => ({ camera_id: e.camera_id, source: paths[i], delay_seconds: Number(e.delay_seconds) }))
        .filter(e => e.source);

      const res = await fetch(`${CONFIG.API_URL}/api/demo/sequence`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": CONFIG.API_KEY },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());

      setStatus("done");
      // Schedule cameras-updated events timed to each camera's delay so the
      // UI sidebar shows each camera as it mounts on the backend.
      const fired = new Set<number>();
      payload.forEach(({ delay_seconds }) => {
        const ms = (delay_seconds + 2) * 1000; // +2s buffer after server mount
        if (!fired.has(ms)) {
          fired.add(ms);
          setTimeout(() => window.dispatchEvent(new CustomEvent("cameras-updated")), ms);
        }
      });
      setTimeout(() => { onLaunched(); onClose(); }, 1800);
    } catch (e: any) {
      setError(e?.message || "Launch failed");
      setStatus("idle");
    }
  };

  const isLoading = status === "uploading" || status === "launching";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-panel border border-border rounded-lg w-[560px] p-5 relative">
        <button onClick={onClose} disabled={isLoading} className="absolute top-3 right-3 text-muted-foreground hover:text-foreground disabled:opacity-40">
          <X size={14} />
        </button>

        <div className="text-[11px] font-mono text-primary uppercase tracking-widest mb-1 flex items-center gap-2">
          <Play size={13} /> Demo Sequence
        </div>
        <div className="text-[10px] text-muted-foreground mb-4">
          Upload 3 videos of the same person across different cameras. Each starts after a delay to simulate movement.
        </div>

        {/* Column headers */}
        <div className="grid grid-cols-[100px_1fr_70px] gap-2 mb-1 px-1">
          <span className="text-[8px] font-mono text-muted-foreground uppercase tracking-widest">Camera ID</span>
          <span className="text-[8px] font-mono text-muted-foreground uppercase tracking-widest">Video File</span>
          <span className="text-[8px] font-mono text-muted-foreground uppercase tracking-widest">Delay (s)</span>
        </div>

        {entries.map((entry, i) => (
          <div key={i} className="grid grid-cols-[100px_1fr_70px] gap-2 mb-2 items-center">
            {/* Camera ID */}
            <input
              className="bg-background border border-border px-2 py-1.5 text-[10px] font-mono w-full"
              value={entry.camera_id}
              onChange={e => updateEntry(i, { camera_id: e.target.value })}
              disabled={isLoading}
            />

            {/* File picker */}
            <div>
              <input
                ref={fileRefs[i]}
                type="file"
                accept="video/*"
                className="hidden"
                onChange={e => e.target.files?.[0] && handleFileSelect(i, e.target.files[0])}
              />
              <button
                onClick={() => fileRefs[i].current?.click()}
                disabled={isLoading}
                className={`w-full flex items-center gap-2 px-3 py-1.5 border text-[10px] font-mono transition-colors ${
                  entry.uploadDone
                    ? "border-green-500/40 text-green-400 bg-green-500/5"
                    : entry.file
                    ? "border-primary/40 text-primary bg-primary/5"
                    : "border-dashed border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
                } disabled:opacity-50`}
              >
                {entry.uploadDone ? (
                  <><CheckCircle2 size={12} className="shrink-0" /><span className="truncate">{entry.file?.name}</span></>
                ) : entry.file ? (
                  <><Upload size={12} className="shrink-0" /><span className="truncate">{entry.file.name}</span></>
                ) : (
                  <><Upload size={12} className="shrink-0" /><span>Browse video…</span></>
                )}
              </button>

              {/* Upload progress bar */}
              {entry.file && !entry.uploadDone && entry.uploadProgress > 0 && (
                <div className="h-0.5 bg-border mt-0.5">
                  <div className="h-full bg-primary transition-all" style={{ width: `${entry.uploadProgress}%` }} />
                </div>
              )}
              {entry.uploadError && (
                <div className="text-[9px] text-red-400 mt-0.5">{entry.uploadError}</div>
              )}
            </div>

            {/* Delay */}
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={0}
                max={300}
                disabled={isLoading}
                className="bg-background border border-border px-2 py-1.5 text-[10px] font-mono w-full text-center"
                value={entry.delay_seconds}
                onChange={e => updateEntry(i, { delay_seconds: Number(e.target.value) })}
              />
            </div>
          </div>
        ))}

        {error && <div className="text-[10px] text-red-400 mb-3">{error}</div>}

        <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
          <div className="text-[9px] font-mono text-muted-foreground">
            {status === "uploading" && "Uploading files…"}
            {status === "launching" && "Launching sequence…"}
            {status === "done" && "✓ Sequence launched!"}
          </div>
          <button
            onClick={launch}
            disabled={isLoading || status === "done" || !entries.some(e => e.file)}
            className="flex items-center gap-2 px-4 py-2 bg-primary/20 text-primary border border-primary/40 text-[10px] font-mono uppercase tracking-wider hover:bg-primary/30 disabled:opacity-40 transition-colors"
          >
            {status === "done" ? <><CheckCircle2 size={12} /> Done!</> : <><Play size={12} /> Launch Sequence</>}
          </button>
        </div>
      </div>
    </div>
  );
}

export function LiveView({ cameras, activeCamera, state, onSwitchCamera, onAddFeed, onFaceClick, onPlateClick, videoFlash }: LiveViewProps) {
  const [layout, setLayout] = useState<"grid" | "focus" | "split">(cameras.length === 1 ? "focus" : "grid");
  const [isPaused, setIsPaused] = useState(false);
  const [demoModalOpen, setDemoModalOpen] = useState(false);
  const [streamProfile, setStreamProfile] = useState<"low" | "balanced" | "high">("balanced");
  const [splitLeft, setSplitLeft] = useState<string>("");
  const [splitRight, setSplitRight] = useState<string>("");

  const splitDefaults = useMemo(() => {
    const left = activeCamera || cameras[0] || "";
    const right = cameras.find((id) => id !== left) || left;
    return { left, right };
  }, [activeCamera, cameras]);

  const handleSelectCamera = useCallback((id: string) => {
    onSwitchCamera(id);
    setLayout("focus");
  }, [onSwitchCamera]);

  const handleRemoveCamera = async () => {
    if (!activeCamera) return;
    if (!confirm(`Remove ${activeCamera} from all active feeds?`)) return;
    try { await apiFetch(`/api/cameras/${activeCamera}`, { method: "DELETE" }); } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent("cameras-updated"));
  };

  const handleStreamProfile = async (profile: "low" | "balanced" | "high") => {
    setStreamProfile(profile);
    if (!activeCamera) return;
    try {
      await apiFetch(
        `/api/video/profile?camera_id=${encodeURIComponent(activeCamera)}&profile=${encodeURIComponent(profile)}`,
        { method: "POST" }
      );
    } catch {
      // ignore; stream continues with existing settings
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* View Header (32px) */}
      <div className="flex items-center justify-between border-b border-border bg-panel px-3 shrink-0" style={{ height: 36 }}>
        {/* Camera tabs */}
        <div className="flex items-center gap-0 overflow-x-auto scrollbar-hide flex-1">
          {cameras.map(id => (
            <button
              key={id}
              onClick={() => handleSelectCamera(id)}
              className={`px-3 py-1 text-[9px] font-mono uppercase whitespace-nowrap border-b-2 transition-all ${
                layout === "focus" && activeCamera === id
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {id}
            </button>
          ))}
          <button onClick={onAddFeed}
            className="px-2 py-1 text-[9px] font-mono text-muted-foreground hover:text-primary transition-all">
            [+]
          </button>
          <button
            onClick={() => setDemoModalOpen(true)}
            className="flex items-center gap-1 px-2 py-1 text-[9px] font-mono text-primary/70 hover:text-primary border border-primary/30 hover:border-primary/60 rounded transition-all ml-1"
            title="Start demo sequence with staggered cameras"
          >
            <Play size={10} /> DEMO
          </button>
        </div>

        {/* Layout toggle + feed controls */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Layout buttons */}
          <div className="flex border border-border">
            <button onClick={() => setLayout("grid")}
              className={`px-2 py-1 text-[9px] transition-all ${layout === "grid" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}
              title="Grid view">
              <LayoutGrid size={12} />
            </button>
            <button onClick={() => setLayout("focus")}
              className={`px-2 py-1 text-[9px] transition-all ${layout === "focus" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}
              title="Focus view">
              <Maximize2 size={12} />
            </button>
            <button
              onClick={() => {
                setLayout("split");
                setSplitLeft((prev) => prev || splitDefaults.left);
                setSplitRight((prev) => prev || splitDefaults.right);
              }}
              className={`px-2 py-1 text-[9px] transition-all ${layout === "split" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}
              title="Split view (2-up)"
            >
              2UP
            </button>
          </div>

          {layout !== "grid" && activeCamera && (
            <>
              <select
                value={streamProfile}
                onChange={(e) => handleStreamProfile(e.target.value as any)}
                className="px-2 py-1 border border-border bg-background text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground transition-all"
                title="Stream quality"
              >
                <option value="low">LOW LATENCY</option>
                <option value="balanced">BALANCED</option>
                <option value="high">HIGH QUALITY</option>
              </select>
              {layout === "split" && (
                <div className="flex items-center gap-1">
                  <select
                    value={splitLeft || splitDefaults.left}
                    onChange={(e) => setSplitLeft(e.target.value)}
                    className="px-2 py-1 border border-border bg-background text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground transition-all"
                    title="Left feed"
                  >
                    {cameras.map((id) => <option key={`l-${id}`} value={id}>{id}</option>)}
                  </select>
                  <select
                    value={splitRight || splitDefaults.right}
                    onChange={(e) => setSplitRight(e.target.value)}
                    className="px-2 py-1 border border-border bg-background text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground transition-all"
                    title="Right feed"
                  >
                    {cameras.map((id) => <option key={`r-${id}`} value={id}>{id}</option>)}
                  </select>
                </div>
              )}
              <button onClick={() => setIsPaused(p => !p)}
                className="flex items-center gap-1 px-2 py-1 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground transition-all">
                <Pause size={11} /> {isPaused ? "RESUME" : "PAUSE"}
              </button>
              <button onClick={handleRemoveCamera}
                className="flex items-center gap-1 px-2 py-1 border border-status-alert/40 text-[9px] font-mono uppercase text-status-alert hover:bg-status-alert/10 transition-all">
                <Trash2 size={11} /> REMOVE
              </button>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {layout === "grid" ? (
          <CameraGrid
            cameras={cameras}
            activeCamera={activeCamera}
            state={state}
            onSelectCamera={handleSelectCamera}
            onAddFeed={onAddFeed}
          />
        ) : layout === "split" ? (
          /* SPLIT VIEW layout */
          <div className="h-full grid overflow-hidden" style={{ gridTemplateColumns: "1fr 300px", gridTemplateRows: "1fr auto" }}>
            {/* Two Videos */}
            <div className="grid gap-2 p-2 overflow-hidden" style={{ minHeight: 0, gridTemplateColumns: "1fr 1fr" }}>
              {!isPaused ? (
                <>
                  <div className="relative overflow-hidden border border-border" style={{ minHeight: 0 }}>
                    <VideoPlayer activeCamera={(splitLeft || splitDefaults.left) || activeCamera} state={state} videoFlash={videoFlash} />
                  </div>
                  <div className="relative overflow-hidden border border-border" style={{ minHeight: 0 }}>
                    <VideoPlayer activeCamera={(splitRight || splitDefaults.right) || activeCamera} state={state} videoFlash={videoFlash} />
                  </div>
                </>
              ) : (
                <div className="col-span-2 w-full h-full flex items-center justify-center bg-background/80 border border-border">
                  <div className="text-center">
                    <CameraIcon size={32} className="text-muted-foreground/40 mx-auto mb-2" />
                    <div className="text-[10px] font-mono text-muted-foreground uppercase">STREAM PAUSED</div>
                  </div>
                </div>
              )}
            </div>

            {/* Intelligence Hub */}
            <div className="border-l border-border overflow-hidden">
              <IntelligenceHub state={state} onFaceClick={onFaceClick} onPlateClick={onPlateClick} />
            </div>

            {/* Metrics Row — spans full width */}
            <div className="col-span-2 border-t border-border">
              <MetricsRow state={state} />
            </div>
          </div>
        ) : (
          /* FOCUS VIEW layout */
          <div className="h-full grid overflow-hidden" style={{ gridTemplateColumns: "1fr 300px", gridTemplateRows: "1fr auto" }}>
            {/* Video */}
            <div className="relative overflow-hidden" style={{ minHeight: 0 }}>
              {!isPaused ? (
                <VideoPlayer activeCamera={activeCamera} state={state} videoFlash={videoFlash} />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-background/80 border border-border">
                  <div className="text-center">
                    <CameraIcon size={32} className="text-muted-foreground/40 mx-auto mb-2" />
                    <div className="text-[10px] font-mono text-muted-foreground uppercase">STREAM PAUSED</div>
                  </div>
                </div>
              )}
            </div>

            {/* Intelligence Hub */}
            <div className="border-l border-border overflow-hidden">
              <IntelligenceHub state={state} onFaceClick={onFaceClick} onPlateClick={onPlateClick} />
            </div>

            {/* Metrics Row — spans full width */}
            <div className="col-span-2 border-t border-border">
              <MetricsRow state={state} />
            </div>
          </div>
        )}
      </div>
      {demoModalOpen && (
        <DemoSequenceModal
          onClose={() => setDemoModalOpen(false)}
          onLaunched={() => window.dispatchEvent(new CustomEvent("cameras-updated"))}
        />
      )}
    </div>
  );
}
