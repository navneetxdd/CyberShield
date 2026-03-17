import { useState, useRef, useCallback } from "react";
import { Upload, Wifi, PlayCircle, Plus, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getConfig } from "@/lib/config";
import { apiFetch } from "@/lib/api";

interface AddFeedModalProps {
  open: boolean;
  onClose: () => void;
  onCameraAdded: (cameraId: string) => void;
}

// ─── Single-upload tab ────────────────────────────────────────────────────────

function UploadTab({ onCameraAdded, onClose }: { onCameraAdded: (id: string) => void; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [cameraId, setCameraId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = useCallback(async () => {
    if (!file) return;
    setUploading(true); setProgress(0);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (cameraId.trim()) formData.append("camera_id", cameraId.trim());
      const data = await new Promise<any>((resolve, reject) => {
        const config = getConfig();
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${config.API_URL}/api/video/upload`);
        if (config.API_KEY) xhr.setRequestHeader("X-API-Key", config.API_KEY);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => { try { resolve(JSON.parse(xhr.responseText)); } catch { reject(new Error("Invalid response")); } };
        xhr.onerror = () => reject(new Error("Network error"));
        xhr.send(formData);
      });
      if (data?.status === "success" && data.camera_id) {
        onCameraAdded(data.camera_id); onClose();
      } else {
        alert("Upload failed: " + (data?.message || "Unknown error"));
      }
    } catch (e: any) {
      alert("Upload error: " + (e?.message || "Check backend connection"));
    } finally { setUploading(false); }
  }, [file, cameraId, onCameraAdded, onClose]);

  return (
    <>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f?.type.startsWith("video/")) setFile(f); }}
        onClick={() => fileInputRef.current?.click()}
        className={`h-28 flex flex-col items-center justify-center cursor-pointer border transition-all ${dragOver ? "border-primary bg-primary/5" : "border-dashed border-border hover:border-primary/50"}`}
      >
        <Upload size={24} className="text-muted-foreground mb-2" />
        <div className="text-[10px] font-mono text-foreground uppercase">DRAG & DROP VIDEO FILE</div>
        <div className="text-[9px] font-mono text-muted-foreground">or click to browse</div>
        <div className="text-[8px] font-mono text-muted-foreground/60 mt-1">MP4 · AVI · MOV · MKV · WEBM</div>
      </div>
      <input ref={fileInputRef} type="file" accept="video/*" className="hidden"
        onChange={e => e.target.files?.[0] && setFile(e.target.files[0])} />
      {file && (
        <div className="flex items-center justify-between border border-border px-3 py-2">
          <div>
            <div className="text-[10px] font-mono text-foreground">{file.name}</div>
            <div className="text-[8px] font-mono text-muted-foreground">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
          </div>
          <button onClick={() => setFile(null)} className="text-muted-foreground hover:text-status-alert text-[9px] font-mono">✕</button>
        </div>
      )}
      <input value={cameraId} onChange={e => setCameraId(e.target.value)} placeholder="CAMERA ID (optional)"
        className="w-full text-[11px] font-mono bg-background border border-border px-3 py-1.5 text-foreground placeholder:text-muted-foreground/50 focus:outline-1 focus:outline-primary" />
      {uploading && (
        <div>
          <div className="h-1 bg-border"><div className="h-full bg-primary transition-all duration-300" style={{ width: `${progress}%` }} /></div>
          <div className="text-[8px] font-mono text-muted-foreground mt-1">UPLOADING... {progress}%</div>
        </div>
      )}
      <button onClick={handleUpload} disabled={!file || uploading}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase tracking-wider hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
        {uploading ? "PROCESSING..." : "UPLOAD & CONNECT"}
      </button>
    </>
  );
}

// ─── Stream tab ───────────────────────────────────────────────────────────────

function StreamTab({ onCameraAdded, onClose }: { onCameraAdded: (id: string) => void; onClose: () => void }) {
  const [streamUrl, setStreamUrl] = useState("");
  const [cameraId, setCameraId] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connTest, setConnTest] = useState<"idle" | "testing" | "ok" | "fail">("idle");

  const handleConnect = async () => {
    if (!streamUrl.trim()) return;
    const camId = cameraId.trim() || `CAM_${Date.now().toString().slice(-6)}`;
    setConnecting(true);
    try {
      const data = await apiFetch(
        `/api/cameras/add?camera_id=${encodeURIComponent(camId)}&source=${encodeURIComponent(streamUrl)}`,
        { method: "POST" }
      ) as any;
      if (data?.status === "success") { onCameraAdded(data.camera_id || camId); onClose(); }
      else alert("Connection failed: " + (data?.detail || "Unknown"));
    } catch (e: any) {
      alert("Connect error: " + e?.message);
    } finally { setConnecting(false); }
  };

  return (
    <>
      <div>
        <label className="text-[8px] font-mono text-muted-foreground uppercase mb-1 block">STREAM URL</label>
        <input value={streamUrl} onChange={e => setStreamUrl(e.target.value)}
          placeholder="rtsp://192.168.1.x:554/stream  or  http://..."
          className="w-full text-[11px] font-mono bg-background border border-border px-3 py-1.5 text-foreground placeholder:text-muted-foreground/50 focus:outline-1 focus:outline-primary" />
        <div className="text-[8px] font-mono text-muted-foreground mt-0.5">Supports RTSP, HTTP MJPEG streams</div>
      </div>
      <div>
        <label className="text-[8px] font-mono text-muted-foreground uppercase mb-1 block">CAMERA ID</label>
        <input value={cameraId} onChange={e => setCameraId(e.target.value)} placeholder="Auto-assigned if empty"
          className="w-full text-[11px] font-mono bg-background border border-border px-3 py-1.5 text-foreground placeholder:text-muted-foreground/50 focus:outline-1 focus:outline-primary" />
      </div>
      <div className="flex gap-2">
        <button onClick={async () => { setConnTest("testing"); try { await apiFetch(`/api/cameras/validate-source?source=${encodeURIComponent(streamUrl)}`, { method: "POST" }); setConnTest("ok"); } catch { setConnTest("fail"); } }}
          disabled={!streamUrl} className="px-3 py-1.5 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground disabled:opacity-40 transition-all">
          TEST CONNECTION
        </button>
        {connTest === "ok" && <span className="text-[9px] font-mono text-status-online self-center">● REACHABLE</span>}
        {connTest === "fail" && <span className="text-[9px] font-mono text-status-alert self-center">● UNREACHABLE</span>}
        {connTest === "testing" && <span className="text-[9px] font-mono text-muted-foreground self-center">TESTING...</span>}
      </div>
      <button onClick={handleConnect} disabled={!streamUrl || connecting}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase tracking-wider hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
        {connecting ? "CONNECTING..." : "CONNECT"}
      </button>
    </>
  );
}

// ─── Demo sequence tab ────────────────────────────────────────────────────────

type RowStatus = "idle" | "uploading" | "staged" | "waiting" | "mounting" | "live" | "error";

interface SeqRow {
  id: number;
  file: File | null;
  cameraId: string;
  delaySec: number;
  progress: number;
  status: RowStatus;
  error: string;
}

const STATUS_LABEL: Record<RowStatus, string> = {
  idle: "", uploading: "UPLOADING...", staged: "STAGED", waiting: "WAITING...",
  mounting: "MOUNTING...", live: "LIVE", error: "ERROR",
};
const STATUS_COLOR: Record<RowStatus, string> = {
  idle: "text-muted-foreground", uploading: "text-primary", staged: "text-status-warning",
  waiting: "text-status-warning", mounting: "text-primary", live: "text-status-online", error: "text-status-alert",
};

let _rowIdCounter = 1;
function makeRow(delaySec = 0): SeqRow {
  return { id: _rowIdCounter++, file: null, cameraId: "", delaySec, progress: 0, status: "idle", error: "" };
}

function DemoSequenceTab({ onCameraAdded }: { onCameraAdded: (id: string) => void }) {
  const [rows, setRows] = useState<SeqRow[]>([makeRow(0), makeRow(5), makeRow(10)]);
  const [launching, setLaunching] = useState(false);
  const fileRefs = useRef<(HTMLInputElement | null)[]>([]);

  const updateRow = (id: number, patch: Partial<SeqRow>) =>
    setRows(prev => prev.map(r => r.id === id ? { ...r, ...patch } : r));

  const handleLaunch = async () => {
    const active = rows.filter(r => r.file !== null);
    if (active.length === 0) return;
    setLaunching(true);

    // Phase 1: upload all files in parallel via /api/video/stage
    const config = getConfig();

    const stageRow = (row: SeqRow): Promise<{ row: SeqRow; stagedPath: string; resolvedCamId: string } | null> =>
      new Promise(resolve => {
        updateRow(row.id, { status: "uploading", progress: 0 });
        const fd = new FormData();
        fd.append("file", row.file!);
        if (row.cameraId.trim()) fd.append("camera_id", row.cameraId.trim());
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${config.API_URL}/api/video/stage`);
        if (config.API_KEY) xhr.setRequestHeader("X-API-Key", config.API_KEY);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) updateRow(row.id, { progress: Math.round((e.loaded / e.total) * 100) });
        };
        xhr.onload = () => {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data?.status === "staged") {
              updateRow(row.id, { status: "staged", progress: 100, cameraId: data.camera_id });
              resolve({ row, stagedPath: data.staged_path, resolvedCamId: data.camera_id });
            } else {
              updateRow(row.id, { status: "error", error: data?.detail || "Stage failed" });
              resolve(null);
            }
          } catch { updateRow(row.id, { status: "error", error: "Invalid response" }); resolve(null); }
        };
        xhr.onerror = () => { updateRow(row.id, { status: "error", error: "Network error" }); resolve(null); };
        xhr.send(fd);
      });

    const results = await Promise.all(active.map(stageRow));

    // Phase 2: mount each staged feed at its configured delay (relative to now)
    const successes = results.filter(Boolean) as { row: SeqRow; stagedPath: string; resolvedCamId: string }[];
    successes.forEach(({ row, stagedPath, resolvedCamId }) => {
      updateRow(row.id, { status: "waiting" });
      setTimeout(async () => {
        updateRow(row.id, { status: "mounting" });
        try {
          const data = await apiFetch(
            `/api/cameras/add?camera_id=${encodeURIComponent(resolvedCamId)}&source=${encodeURIComponent(stagedPath)}`,
            { method: "POST" }
          ) as any;
          if (data?.status === "success") {
            updateRow(row.id, { status: "live" });
            onCameraAdded(resolvedCamId);
            window.dispatchEvent(new CustomEvent("cameras-updated"));
          } else {
            updateRow(row.id, { status: "error", error: data?.detail || "Mount failed" });
          }
        } catch (e: any) {
          updateRow(row.id, { status: "error", error: e?.message || "Mount error" });
        }
      }, row.delaySec * 1000);
    });

    // Don't lock the UI — user can watch progress
    setLaunching(false);
  };

  const hasFiles = rows.some(r => r.file !== null);
  const isRunning = rows.some(r => ["uploading", "waiting", "mounting"].includes(r.status));

  return (
    <div className="space-y-3">
      <div className="text-[8px] font-mono text-muted-foreground leading-relaxed">
        Upload multiple feeds and configure a start delay for each. All files upload first, then cameras go live at their set delays.
      </div>

      {/* Rows */}
      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div key={row.id} className="border border-border p-2 space-y-1.5">
            {/* Row header */}
            <div className="flex items-center justify-between">
              <span className="text-[8px] font-mono text-muted-foreground uppercase">FEED {idx + 1}</span>
              <div className="flex items-center gap-2">
                {row.status !== "idle" && (
                  <span className={`text-[8px] font-mono ${STATUS_COLOR[row.status]}`}>
                    {STATUS_LABEL[row.status]}
                    {row.status === "uploading" && ` ${row.progress}%`}
                    {row.status === "error" && ` — ${row.error}`}
                  </span>
                )}
                {rows.length > 1 && !isRunning && (
                  <button onClick={() => setRows(p => p.filter(r => r.id !== row.id))}
                    className="text-muted-foreground hover:text-status-alert transition-all">
                    <X size={10} />
                  </button>
                )}
              </div>
            </div>

            {/* Upload bar (when uploading) */}
            {row.status === "uploading" && (
              <div className="h-0.5 bg-border"><div className="h-full bg-primary transition-all" style={{ width: `${row.progress}%` }} /></div>
            )}

            {/* File picker */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => fileRefs.current[idx]?.click()}
                disabled={isRunning}
                className={`flex-1 text-left px-2 py-1 border text-[9px] font-mono transition-all disabled:opacity-40 ${
                  row.file ? "border-primary/40 text-foreground" : "border-dashed border-border text-muted-foreground hover:border-primary/50"
                }`}
              >
                {row.file ? row.file.name : "CLICK TO SELECT VIDEO..."}
              </button>
              {row.file && !isRunning && (
                <button onClick={() => updateRow(row.id, { file: null, status: "idle", progress: 0, error: "" })}
                  className="text-muted-foreground hover:text-status-alert transition-all">
                  <X size={12} />
                </button>
              )}
              <input ref={el => { fileRefs.current[idx] = el; }} type="file" accept="video/*" className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) updateRow(row.id, { file: f, status: "idle", error: "" }); e.target.value = ""; }} />
            </div>

            {/* Camera ID + Delay */}
            <div className="grid grid-cols-2 gap-2">
              <input value={row.cameraId} onChange={e => updateRow(row.id, { cameraId: e.target.value })}
                placeholder={`camera_${idx + 1}`} disabled={isRunning}
                className="text-[9px] font-mono bg-background border border-border px-2 py-1 text-foreground placeholder:text-muted-foreground/40 focus:outline-1 focus:outline-primary disabled:opacity-40" />
              <div className="flex items-center gap-1">
                <span className="text-[8px] font-mono text-muted-foreground whitespace-nowrap">DELAY (s)</span>
                <input
                  type="number" min={0} step={1}
                  value={row.delaySec}
                  onChange={e => updateRow(row.id, { delaySec: Math.max(0, parseInt(e.target.value) || 0) })}
                  disabled={isRunning}
                  className="w-full text-[9px] font-mono bg-background border border-border px-2 py-1 text-foreground focus:outline-1 focus:outline-primary disabled:opacity-40"
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Add row */}
      {!isRunning && (
        <button onClick={() => setRows(p => [...p, makeRow(0)])}
          className="flex items-center gap-1 text-[9px] font-mono text-muted-foreground hover:text-foreground transition-all">
          <Plus size={11} /> ADD FEED ROW
        </button>
      )}

      {/* Launch */}
      <button onClick={handleLaunch} disabled={!hasFiles || launching || isRunning}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase tracking-wider hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
        <PlayCircle size={13} />
        {isRunning ? "SEQUENCE RUNNING..." : "LAUNCH SEQUENCE"}
      </button>
    </div>
  );
}

// ─── Modal shell ──────────────────────────────────────────────────────────────

export function AddFeedModal({ open, onClose, onCameraAdded }: AddFeedModalProps) {
  const [tab, setTab] = useState<"upload" | "stream" | "demo">("upload");

  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="w-[520px] max-w-[520px] bg-panel border border-border p-0">
        <DialogHeader className="px-4 pt-4 pb-2 border-b border-border">
          <DialogTitle className="text-[11px] font-mono tracking-widest text-primary uppercase">ADD VIDEO SOURCE</DialogTitle>
          <p className="text-[9px] font-mono text-muted-foreground">Connect a live stream, upload a recording, or run a staggered demo sequence</p>
        </DialogHeader>

        {/* Tabs */}
        <div className="flex border-b border-border">
          {[
            { id: "upload" as const, icon: <Upload size={11} />, label: "UPLOAD FILE" },
            { id: "stream" as const, icon: <Wifi size={11} />, label: "LIVE STREAM" },
            { id: "demo"   as const, icon: <PlayCircle size={11} />, label: "DEMO SEQUENCE" },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 text-[9px] font-mono uppercase tracking-wider border-b-2 transition-all ${
                tab === t.id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}>
              {t.icon}{t.label}
            </button>
          ))}
        </div>

        <div className="p-4 space-y-3 max-h-[70vh] overflow-y-auto">
          {tab === "upload" && <UploadTab onCameraAdded={onCameraAdded} onClose={onClose} />}
          {tab === "stream" && <StreamTab onCameraAdded={onCameraAdded} onClose={onClose} />}
          {tab === "demo"   && <DemoSequenceTab onCameraAdded={onCameraAdded} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}
