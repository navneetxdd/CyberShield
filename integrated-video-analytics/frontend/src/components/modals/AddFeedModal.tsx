import { useState, useRef, useCallback } from "react";
import { Upload, Wifi } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CONFIG } from "@/lib/config";
import { apiFetch } from "@/lib/api";

interface AddFeedModalProps {
  open: boolean;
  onClose: () => void;
  onCameraAdded: (cameraId: string) => void;
}

export function AddFeedModal({ open, onClose, onCameraAdded }: AddFeedModalProps) {
  const [tab, setTab] = useState<"stream" | "upload">("upload");
  const [streamUrl, setStreamUrl] = useState("");
  const [cameraId, setCameraId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [connTest, setConnTest] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => setFile(f);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("video/")) handleFile(f);
  };

  const handleUpload = useCallback(async () => {
    if (!file) return;
    setUploading(true); setProgress(0);

    try {
      const formData = new FormData();
      formData.append("file", file);
      if (cameraId.trim()) formData.append("camera_id", cameraId.trim());

      // Use XHR for real progress tracking
      const data = await new Promise<any>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${CONFIG.API_URL}/api/video/upload`);
        xhr.setRequestHeader("X-API-Key", CONFIG.API_KEY);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { reject(new Error("Invalid response")); }
        };
        xhr.onerror = () => reject(new Error("Network error"));
        xhr.send(formData);
      });
      if (data?.status === "success" && data.camera_id) {
        onCameraAdded(data.camera_id);
        onClose();
      } else {
        alert("Upload failed: " + (data?.message || "Unknown error"));
      }
    } catch (e: any) {
      alert("Upload error: " + (e?.message || "Check backend connection"));
    } finally {
      setUploading(false);
    }
  }, [file, cameraId, onCameraAdded, onClose]);

  const handleConnect = async () => {
    if (!streamUrl.trim()) return;
    const camId = cameraId.trim() || `CAM_${Date.now().toString().slice(-6)}`;

    setUploading(true);
    try {
      const data = await apiFetch(
        `/api/cameras/add?camera_id=${encodeURIComponent(camId)}&source=${encodeURIComponent(streamUrl)}`,
        { method: "POST" }
      ) as any;
      if (data?.status === "success") { onCameraAdded(data.camera_id || camId); onClose(); }
      else alert("Connection failed: " + (data?.detail || "Unknown"));
    } catch (e: any) {
      alert("Connect error: " + (e?.message));
    } finally {
      setUploading(false);
    }
  };

  const testConnection = async () => {
    setConnTest("testing");
    try {
      await fetch(streamUrl, { method: "HEAD", mode: "no-cors" });
      setConnTest("ok");
    } catch { setConnTest("fail"); }
  };

  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="w-[480px] max-w-[480px] bg-panel border border-border p-0">
        <DialogHeader className="px-4 pt-4 pb-2 border-b border-border">
          <DialogTitle className="text-[11px] font-mono tracking-widest text-primary uppercase">ADD VIDEO SOURCE</DialogTitle>
          <p className="text-[9px] font-mono text-muted-foreground">Connect a live stream or upload a recording</p>
        </DialogHeader>

        {/* Tabs */}
        <div className="flex border-b border-border">
          {[
            { id: "upload" as const, icon: <Upload size={11} />, label: "UPLOAD FILE" },
            { id: "stream" as const, icon: <Wifi size={11} />, label: "LIVE STREAM" },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 text-[9px] font-mono uppercase tracking-wider border-b-2 transition-all ${
                tab === t.id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}>
              {t.icon}{t.label}
            </button>
          ))}
        </div>

        <div className="p-4 space-y-3">
          {tab === "upload" && (
            <>
              {/* Drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`h-28 flex flex-col items-center justify-center cursor-pointer border transition-all ${
                  dragOver ? "border-primary bg-primary/5" : "border-dashed border-border hover:border-primary/50"
                }`}
              >
                <Upload size={24} className="text-muted-foreground mb-2" />
                <div className="text-[10px] font-mono text-foreground uppercase">DRAG & DROP VIDEO FILE</div>
                <div className="text-[9px] font-mono text-muted-foreground">or click to browse</div>
                <div className="text-[8px] font-mono text-muted-foreground/60 mt-1">MP4 · AVI · MOV · MKV · WEBM</div>
              </div>
              <input ref={fileInputRef} type="file" accept="video/*" className="hidden"
                onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />

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
                  <div className="h-1 bg-border">
                    <div className="h-full bg-primary transition-all duration-300" style={{ width: `${progress}%` }} />
                  </div>
                  <div className="text-[8px] font-mono text-muted-foreground mt-1">UPLOADING... {progress}%</div>
                </div>
              )}

              <button onClick={handleUpload} disabled={!file || uploading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase tracking-wider hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
                {uploading ? "PROCESSING..." : "UPLOAD & CONNECT"}
              </button>
            </>
          )}

          {tab === "stream" && (
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
                <input value={cameraId} onChange={e => setCameraId(e.target.value)}
                  placeholder="Auto-assigned if empty"
                  className="w-full text-[11px] font-mono bg-background border border-border px-3 py-1.5 text-foreground placeholder:text-muted-foreground/50 focus:outline-1 focus:outline-primary" />
                <div className="text-[8px] font-mono text-muted-foreground mt-0.5">Letters, numbers, hyphens only</div>
              </div>

              <div className="flex gap-2">
                <button onClick={testConnection} disabled={!streamUrl}
                  className="px-3 py-1.5 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground disabled:opacity-40 transition-all">
                  TEST CONNECTION
                </button>
                {connTest === "ok" && <span className="text-[9px] font-mono text-status-online self-center">● REACHABLE</span>}
                {connTest === "fail" && <span className="text-[9px] font-mono text-status-alert self-center">● UNREACHABLE</span>}
                {connTest === "testing" && <span className="text-[9px] font-mono text-muted-foreground self-center">TESTING...</span>}
              </div>

              <button onClick={handleConnect} disabled={!streamUrl || uploading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase tracking-wider hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
                {uploading ? "CONNECTING..." : "CONNECT"}
              </button>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
