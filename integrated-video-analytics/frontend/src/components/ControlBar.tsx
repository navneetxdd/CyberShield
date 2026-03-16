import { useState, useEffect, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { CyberShieldState } from "../pages/Index";
import { apiFetch, apiUpload } from "../lib/api";

interface ControlBarProps {
  cameras: string[];
  activeCamera: string;
  isConnected: boolean;
  state: CyberShieldState;
  onSwitchCamera: (camId: string) => void;
  onToggleWatchlist?: () => void;
  onOpenSummary?: () => void;
  watchlistOpen?: boolean;
}

export function ControlBar({
  cameras, activeCamera, isConnected, state, onSwitchCamera,
  onToggleWatchlist, onOpenSummary, watchlistOpen
}: ControlBarProps) {
  const [uptime, setUptime] = useState("00:00:00");
  const [glitchFeed, setGlitchFeed] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Uptime counter
  useEffect(() => {
    const interval = setInterval(() => {
      setUptime((prev) => {
        const parts = prev.split(":").map(Number);
        parts[2]++;
        if (parts[2] >= 60) { parts[2] = 0; parts[1]++; }
        if (parts[1] >= 60) { parts[1] = 0; parts[0]++; }
        return parts.map((p) => String(p).padStart(2, "0")).join(":");
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleFeedSwitch = useCallback((feedId: string) => {
    setGlitchFeed(feedId);
    setTimeout(() => { onSwitchCamera(feedId); setGlitchFeed(null); }, 150);
  }, [onSwitchCamera]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    try {
      const data = await apiUpload("/api/video/upload", file) as any;
      if (data?.status === "success" && data.camera_id) {
        onSwitchCamera(data.camera_id);
        window.dispatchEvent(new CustomEvent('cameras-updated'));
      }
    } catch (error: any) {
      alert(`Upload failed: ${error?.message || "Check backend connection."}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleAddStream = async () => {
    const url = prompt("Enter stream URL (YouTube, RTSP, HTTP, etc.):");
    if (!url) return;
    setIsUploading(true);
    try {
      const cameraId = `CAM_${Date.now().toString().slice(-6)}`;
      const data = await apiFetch(
        `/api/cameras/add?camera_id=${encodeURIComponent(cameraId)}&source=${encodeURIComponent(url)}`,
        { method: "POST" }
      ) as any;
      if (data?.status === "success" && data.camera_id) {
        onSwitchCamera(data.camera_id);
        window.dispatchEvent(new CustomEvent('cameras-updated'));
      }
    } catch (error: any) {
      alert(`Stream failed: ${error?.message || "Check backend connection at port 8080."}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDemoMode = () => {
    if (!isFullscreen) {
      document.documentElement.requestFullscreen?.();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen?.();
      setIsFullscreen(false);
    }
  };

  // Module status pills
  const anprReady = state.plate_detector_ready;
  const frsReady = state.recent_faces && state.recent_faces.length > 0 || (state as any).faces_detected > 0;
  const vehicleReady = state.vehicle_count >= 0;
  const crowdReady = state.people_count >= 0;

  const ModulePill = ({ label, active }: { label: string; active: boolean }) => (
    <div className={`flex items-center gap-1 px-1.5 py-0.5 border text-[7px] font-mono uppercase tracking-widest ${
      active
        ? "border-status-online/40 bg-status-online/10 text-status-online"
        : "border-status-warning/40 text-status-warning"
    }`}>
      <div className={`w-1 h-1 rounded-full ${active ? "bg-status-online animate-pulse" : "bg-status-warning animate-pulse"}`} />
      {label} {active ? "●" : "○"}
    </div>
  );

  return (
    <header className="col-span-12 flex items-center justify-between border border-border bg-panel px-3 py-1.5 gap-2">
      <div className="flex items-center gap-2 flex-wrap">
        {/* System ID */}
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-primary glow-cyan" />
          <span className="font-mono text-[10px] tracking-[0.2em] text-primary uppercase glow-cyan">ARGUS_V4.2</span>
        </div>
        <div className="w-px h-4 bg-border" />

        {/* Classification */}
        <div className="border border-status-warning/30 px-2 py-0.5">
          <span className="font-mono text-[9px] tracking-[0.2em] text-status-warning uppercase">TS//SCI</span>
        </div>
        <div className="w-px h-4 bg-border" />

        {/* Module Pills (B5.1) */}
        <div className="flex gap-1">
          <ModulePill label="VEH" active={vehicleReady} />
          <ModulePill label="ANPR" active={!!anprReady} />
          <ModulePill label="FRS" active={!!frsReady} />
          <ModulePill label="CROWD" active={crowdReady} />
        </div>
        <div className="w-px h-4 bg-border" />

        {/* Feed Nav */}
        <nav className="flex gap-1 overflow-x-auto max-w-xs scrollbar-hide">
          {cameras.length === 0 && (
            <span className="text-[9px] font-mono text-muted-foreground uppercase">NO_FEEDS</span>
          )}
          {cameras.map((feedId) => (
            <button
              key={feedId}
              onClick={() => handleFeedSwitch(feedId)}
              className={`px-2 py-1 text-[9px] font-mono tracking-wider border transition-all duration-100 uppercase relative whitespace-nowrap ${
                glitchFeed === feedId ? "animate-glitch" : ""
              } ${
                activeCamera === feedId
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground"
              }`}
            >
              <div className="flex items-center gap-1.5">
                <div className={`w-1 h-1 ${activeCamera === feedId && isConnected ? "bg-status-online" : "bg-status-warning animate-pulse"}`} />
                {feedId}
              </div>
              {activeCamera === feedId && <div className="absolute bottom-0 left-0 w-full h-px bg-primary glow-cyan" />}
            </button>
          ))}
        </nav>
        <div className="w-px h-4 bg-border" />

        {/* Add Stream */}
        <button
          onClick={handleAddStream}
          disabled={isUploading}
          className={`px-2 py-1 text-[9px] font-mono tracking-wider border transition-all uppercase ${
            isUploading ? "border-primary/50 text-primary/50 cursor-not-allowed" : "border-border text-primary hover:border-primary/50 hover:bg-primary/10 bg-primary/5"
          }`}
        >
          + STREAM
        </button>

        {/* Upload */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="px-2 py-1 text-[9px] font-mono tracking-wider border border-border text-muted-foreground hover:border-primary/50 hover:text-foreground uppercase transition-all"
        >
          {isUploading ? "UPLOADING..." : "↑ UPLOAD"}
        </button>
        <input type="file" ref={fileInputRef} onChange={handleFileUpload} accept="video/*" className="hidden" />

        {/* Watchlist Toggle */}
        <button
          onClick={onToggleWatchlist}
          className={`px-2 py-1 text-[9px] font-mono tracking-wider border uppercase transition-all ${
            watchlistOpen ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground"
          }`}
        >
          WATCHLIST [W]
        </button>

        {/* Summary */}
        <button
          onClick={onOpenSummary}
          className="px-2 py-1 text-[9px] font-mono tracking-wider border border-border text-muted-foreground hover:border-primary/50 hover:text-foreground uppercase transition-all"
        >
          SUMMARY [S]
        </button>

        {/* Analytics link */}
        <Link
          to="/analytics"
          className="px-2 py-1 text-[9px] font-mono tracking-wider border border-border text-muted-foreground hover:border-primary/50 hover:text-foreground uppercase transition-all"
        >
          ANALYTICS [A]
        </Link>
      </div>

      {/* Telemetry + Status */}
      <div className="flex gap-3 font-mono text-[9px] tracking-wider items-center shrink-0">
        <div className="flex items-center gap-3 border-r border-border pr-3">
          <span className="text-muted-foreground">LAT: <span className="text-primary tabular">{Math.round(state.inference_latency_ms)}MS</span></span>
          <span className="text-muted-foreground">FPS: <span className="text-primary tabular">{state.stream_fps.toFixed(1)}</span></span>
          <span className="text-muted-foreground">CROWD: <span className={`tabular ${state.crowd_density === "High" ? "text-status-alert" : state.crowd_density === "Medium" ? "text-status-warning" : "text-primary"}`}>{state.crowd_density}</span></span>
        </div>
        <span className="text-muted-foreground">UT: <span className="text-foreground tabular">{uptime}</span></span>

        {/* Demo / Fullscreen Button (B5.2) */}
        <button
          onClick={handleDemoMode}
          className="px-2 py-0.5 border border-primary/30 text-primary/70 text-[9px] font-mono uppercase hover:border-primary hover:text-primary transition-all"
          title="Enter fullscreen demo mode"
        >
          {isFullscreen ? "⊡ EXIT" : "⛶ DEMO"}
        </button>

        {/* Connection dot */}
        <div className="flex items-center gap-1.5 border border-status-online/30 px-2 py-0.5">
          <div className={`w-1.5 h-1.5 ${isConnected ? "bg-status-online animate-pulse" : "bg-status-alert"}`} />
          <span className={isConnected ? "text-status-online uppercase" : "text-status-alert uppercase"}>
            {isConnected ? "SYS_NOMINAL" : "SYS_OFFLINE"}
          </span>
        </div>
      </div>
    </header>
  );
}
