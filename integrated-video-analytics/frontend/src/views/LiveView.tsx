import { useState, useCallback, useMemo } from "react";
import { Plus, Pause, Camera as CameraIcon, Trash2, LayoutGrid, Maximize2, Play, X } from "lucide-react";
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

function DemoSequenceModal({ onClose, onLaunched }: { onClose: () => void; onLaunched: () => void }) {
  const [entries, setEntries] = useState([
    { camera_id: "camera_1", source: "", delay_seconds: 0 },
    { camera_id: "camera_2", source: "", delay_seconds: 15 },
    { camera_id: "camera_3", source: "", delay_seconds: 30 },
  ]);
  const [launching, setLaunching] = useState(false);
  const [done, setDone] = useState(false);

  const updateEntry = (i: number, field: string, value: any) => {
    setEntries(prev => prev.map((e, idx) => idx === i ? { ...e, [field]: value } : e));
  };

  const launch = async () => {
    const valid = entries.filter(e => e.source.trim());
    if (!valid.length) return;
    setLaunching(true);
    try {
      const payload = valid.map(e => ({ ...e, delay_seconds: Number(e.delay_seconds) }));
      await fetch("/api/demo/sequence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setDone(true);
      setTimeout(() => { onLaunched(); onClose(); }, 1500);
    } catch {
      /* ignore */
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-panel border border-border rounded-lg w-[500px] p-5 relative">
        <button onClick={onClose} className="absolute top-3 right-3 text-muted-foreground hover:text-foreground">
          <X size={14} />
        </button>
        <div className="text-[11px] font-mono text-primary uppercase tracking-widest mb-4 flex items-center gap-2">
          <Play size={13} /> Demo Sequence
        </div>
        <div className="text-[10px] text-muted-foreground mb-4">
          Configure 3 camera feeds with staggered start times to simulate a person moving across cameras.
        </div>
        {entries.map((entry, i) => (
          <div key={i} className="flex items-center gap-2 mb-2">
            <input
              className="bg-background border border-border rounded px-2 py-1 text-[10px] font-mono w-24"
              value={entry.camera_id}
              onChange={e => updateEntry(i, "camera_id", e.target.value)}
              placeholder="Camera ID"
            />
            <input
              className="bg-background border border-border rounded px-2 py-1 text-[10px] font-mono flex-1"
              value={entry.source}
              onChange={e => updateEntry(i, "source", e.target.value)}
              placeholder="Video path or URL"
            />
            <div className="flex items-center gap-1">
              <span className="text-[9px] text-muted-foreground">+</span>
              <input
                type="number"
                min={0}
                max={300}
                className="bg-background border border-border rounded px-2 py-1 text-[10px] font-mono w-14 text-center"
                value={entry.delay_seconds}
                onChange={e => updateEntry(i, "delay_seconds", e.target.value)}
              />
              <span className="text-[9px] text-muted-foreground">s</span>
            </div>
          </div>
        ))}
        <div className="flex justify-end mt-4">
          <button
            onClick={launch}
            disabled={launching || done}
            className="flex items-center gap-2 px-4 py-2 bg-primary/20 text-primary border border-primary/40 rounded text-[10px] font-mono uppercase tracking-wider hover:bg-primary/30 disabled:opacity-50"
          >
            <Play size={12} />
            {done ? "Launched!" : launching ? "Launching..." : "Launch Sequence"}
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
