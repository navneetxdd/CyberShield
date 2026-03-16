import { useState, useEffect, useCallback, useRef } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Sidebar, ViewType } from "@/components/layout/Sidebar";
import { LiveView } from "@/views/LiveView";
import { WatchlistView } from "@/views/WatchlistView";
import { SettingsView } from "@/views/SettingsView";
import { OSINTView } from "@/views/OSINTView";
import { AlertOverlay } from "@/components/AlertOverlay";
import { AddFeedModal } from "@/components/modals/AddFeedModal";
import { PlateDetailModal } from "@/components/modals/PlateDetailModal";
import { QuickEnrollModal } from "@/components/modals/QuickEnrollModal";
import { AlertHistoryPopover } from "@/components/modals/AlertHistoryPopover";
import { apiFetch } from "@/lib/api";
import { useBackendStream } from "@/hooks/useBackendStream";
import "@/prompt-c-additions.css";
import Analytics from "@/pages/Analytics";

// Re-export so existing imports work
export interface CyberShieldState {
  vehicle_count: number;
  people_count: number;
  stream_fps: number;
  analytics_fps?: number;
  inference_latency_ms: number;
  crowd_density: string;
  is_processing: boolean;
  vehicle_types: Record<string, number>;
  vehicle_current_types?: Record<string, number>;
  gender_stats: Record<string, number>;
  recent_plates: any[];
  recent_faces: any[];
  recent_vehicles: any[];
  event_logs: any[];
  system_health?: any;
  zone_count?: number;
  plate_detector_ready?: boolean;
  device?: string;
  faces_detected?: number;
  plates_detected?: number;
  people_total_count?: number;
}

const defaultState: CyberShieldState = {
  vehicle_count: 0, people_count: 0, stream_fps: 0,
  inference_latency_ms: 0, crowd_density: "Low",
  is_processing: false,
  vehicle_types: { car: 0, motorcycle: 0, bus: 0, truck: 0 },
  gender_stats: { Man: 0, Woman: 0, Unknown: 0 },
  recent_plates: [], recent_faces: [], recent_vehicles: [], event_logs: [],
};

const Index = () => {
  const [cameras, setCameras] = useState<string[]>([]);
  const [activeCamera, setActiveCamera] = useState("");
  const [activeView, setActiveView] = useState<ViewType>("live");
  const [addFeedOpen, setAddFeedOpen] = useState(false);
  const [alertHistory, setAlertHistory] = useState<any[]>([]);
  const [videoFlash, setVideoFlash] = useState(false);
  const [state, setState] = useState<CyberShieldState>(defaultState);
  
  // Drilled-down detail modals
  const [selectedPlate, setSelectedPlate] = useState<any>(null);
  const [selectedFace, setSelectedFace] = useState<any>(null);
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);

  const fetchCameras = useCallback(async () => {
    try {
      const data = await apiFetch("/api/cameras") as any;
      const cams = (data?.cameras || []).map((c: any) => c.camera_id);
      setCameras(cams);
      if (cams.length > 0 && !activeCamera) setActiveCamera(cams[0]);
    } catch { /* offline */ }
  }, [activeCamera]);

  useEffect(() => { fetchCameras(); }, [fetchCameras]);
  useEffect(() => {
    const h = () => fetchCameras();
    window.addEventListener("cameras-updated", h);
    return () => window.removeEventListener("cameras-updated", h);
  }, [fetchCameras]);

  const { data: wsData, connected } = useBackendStream(activeCamera);
  useEffect(() => { if (wsData) setState(p => ({ ...p, ...wsData })); }, [wsData]);

  // Collect watchlist alert events for the counter
  useEffect(() => {
    const newAlerts = (state.event_logs || []).filter(e => e?.type?.includes("Watchlist") || e?.type?.includes("Alert"));
    if (newAlerts.length > alertHistory.length) {
      setAlertHistory(newAlerts);
    }
  }, [state.event_logs]);

  const handleCameraAdded = useCallback((id: string) => {
    setCameras(p => p.includes(id) ? p : [...p, id]);
    setActiveCamera(id);
    setActiveView("live");
    setAddFeedOpen(false);
    window.dispatchEvent(new CustomEvent("cameras-updated"));
  }, []);

  // Keyboard shortcuts (Prompt C §10.10)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key.toLowerCase()) {
        case "l": setActiveView("live"); break;
        case "a": setActiveView("analytics"); break;
        case "w": setActiveView("watchlist"); break;
        case "o": setActiveView("osint"); break;
        case "n": setAddFeedOpen(true); break;
        case "escape": setAddFeedOpen(false); break;
        case "1": case "2": case "3": case "4": case "5":
        case "6": case "7": case "8": {
          const idx = parseInt(e.key) - 1;
          if (cameras[idx]) setActiveCamera(cameras[idx]);
          break;
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [cameras]);

  // Narrow screen detection (Prompt C §12)
  const [tooNarrow, setTooNarrow] = useState(window.innerWidth < 1024);
  useEffect(() => {
    const check = () => setTooNarrow(window.innerWidth < 1024);
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  if (tooNarrow) {
    return (
      <div className="h-screen flex flex-col items-center justify-center bg-background text-center px-8">
        <div className="text-[24px] font-mono font-bold text-primary mb-2">DISPLAY TOO NARROW</div>
        <div className="text-[12px] font-mono text-muted-foreground mb-1">CyberShield requires a minimum 1024px wide display.</div>
        <div className="text-[11px] font-mono text-muted-foreground/60">Rotate device or use a larger screen.</div>
      </div>
    );
  }

  const systemHealth = state.system_health
    ? {
        cpu: state.system_health.cpu ?? 0,
        ram: state.system_health.ram ?? 0,
        gpu: state.system_health.gpu ?? 0,
        gpu_mem: state.system_health.gpu_mem,
        cpu_temp: state.system_health.cpu_temp,
        gpu_temp: state.system_health.gpu_temp,
        throughput: state.system_health.throughput,
      }
    : undefined;

  return (
    <div
      className="h-screen bg-background text-foreground font-mono overflow-hidden"
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gridTemplateRows: "44px 1fr",
      }}
    >
      {/* Subtle scanline overlay */}
      <div className="scanline-overlay" />

      {/* TOP BAR — spans full width */}
      <div style={{ gridColumn: "1 / -1", gridRow: "1 / 2" }}>
        <AlertHistoryPopover alerts={alertHistory}>
          <div>
            <TopBar
              state={state}
              activeCamera={activeCamera}
              alertCount={alertHistory.length}
              notificationsEnabled={notificationsEnabled}
              onToggleNotifications={() => setNotificationsEnabled(p => !p)}
              onNavigate={setActiveView}
              onOpenAddFeed={() => setAddFeedOpen(true)}
              onOpenAlertHistory={() => {}} // Popover handles this now by wrapping
              onOpenSettings={() => setActiveView("settings")}
            />
          </div>
        </AlertHistoryPopover>
      </div>

      {/* SIDEBAR */}
      <Sidebar
        activeView={activeView}
        onNavigate={setActiveView}
        systemHealth={systemHealth}
      />

      {/* CONTENT AREA */}
      <div style={{ gridColumn: "2 / 3", gridRow: "2 / 3" }} className="overflow-hidden">
        {activeView === "live" && (
          <LiveView
            cameras={cameras}
            activeCamera={activeCamera}
            state={state}
            onSwitchCamera={setActiveCamera}
            onAddFeed={() => setAddFeedOpen(true)}
            onFaceClick={setSelectedFace}
            onPlateClick={setSelectedPlate}
            videoFlash={videoFlash}
          />
        )}
        {activeView === "analytics" && (
          <div className="h-full overflow-auto">
            <Analytics />
          </div>
        )}
        {activeView === "watchlist" && (
          <WatchlistView state={state} activeCamera={activeCamera} />
        )}
        {activeView === "osint" && <OSINTView />}
        {activeView === "settings" && <SettingsView />}
      </div>

      {/* Alert Overlay (global) */}
      <AlertOverlay 
        eventLogs={state.event_logs} 
        onFlash={setVideoFlash} 
        enabled={notificationsEnabled}
      />

      {/* Add Feed Modal */}
      <AddFeedModal
        open={addFeedOpen}
        onClose={() => setAddFeedOpen(false)}
        onCameraAdded={handleCameraAdded}
      />

      <PlateDetailModal 
        plate={selectedPlate} 
        open={!!selectedPlate} 
        onClose={() => setSelectedPlate(null)} 
      />

      <QuickEnrollModal 
        face={selectedFace} 
        open={!!selectedFace} 
        onClose={() => setSelectedFace(null)} 
      />
    </div>
  );
};

export default Index;
