import { useState, useEffect, useRef } from "react";
import { AlertTriangle, Plus, Download, ChevronDown, Bell, BellOff } from "lucide-react";
import { CyberShieldState } from "../../pages/Index";
import { CONFIG } from "../../lib/config";
import { ViewType } from "./Sidebar";

interface TopBarProps {
  state: CyberShieldState;
  activeCamera: string;
  alertCount: number;
  notificationsEnabled: boolean;
  onToggleNotifications: () => void;
  onNavigate: (view: ViewType) => void;
  onOpenAddFeed: () => void;
  onOpenAlertHistory: () => void;
  onOpenSettings: () => void;
}

function ModulePill({ label, active, demo }: { label: string; active: boolean; demo: boolean }) {
  const on = active || demo;
  return (
    <div className={`flex items-center gap-1.5 text-[9px] font-mono uppercase tracking-wider ${on ? "text-status-online" : "text-status-warning"}`}>
      <div className={`w-1.5 h-1.5 rounded-full ${on ? "bg-status-online animate-pulse" : "bg-status-warning animate-pulse"}`} />
      {label}
    </div>
  );
}

export function TopBar({ state, activeCamera, alertCount, notificationsEnabled, onToggleNotifications, onNavigate, onOpenAddFeed, onOpenAlertHistory, onOpenSettings }: TopBarProps) {
  const [clock, setClock] = useState({ time: "", date: "" });
  const [isDownloading, setIsDownloading] = useState(false);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock({
        time: now.toLocaleTimeString("en-GB", { hour12: false }),
        date: now.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase(),
      });
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const handleDownloadReport = async () => {
    if (!activeCamera) return;
    setIsDownloading(true);
    try {
      const url = `${CONFIG.API_URL}/api/reports/download?camera_id=${activeCamera}&api_key=${CONFIG.API_KEY}`;
      const res = await fetch(url);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `cybershield_report_${Date.now()}.pdf`;
      a.click();
    } catch {
      alert("Report generation failed. Check backend connection.");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <header
      style={{ gridColumn: "1 / -1", gridRow: "1 / 2", height: 44 }}
      className="flex items-center justify-between bg-panel border-b border-border px-3 shrink-0"
    >
      {/* LEFT: Logo + Module Pills */}
      <div className="flex items-center gap-3">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 bg-primary/10 border border-primary/60 flex items-center justify-center">
            <span className="text-[9px] font-mono font-bold text-primary">CS</span>
          </div>
          <div>
            <div className="text-[11px] font-mono font-semibold text-primary tracking-widest leading-none">CYBERSHIELD</div>
            <div className="text-[8px] font-mono text-muted-foreground tracking-wider leading-none mt-0.5">SENTINEL COMMAND</div>
          </div>
        </div>
        <div className="w-px h-5 bg-border" />

        {/* Module Pills */}
        <div className="flex items-center gap-4">
          <ModulePill label="VEHICLE" active={(state.vehicle_count ?? 0) > 0} demo={false} />
          <ModulePill label="ANPR" active={!!state.plate_detector_ready} demo={false} />
          <ModulePill label="FRS" active={(state.recent_faces?.length ?? 0) > 0 || (state as any).faces_detected > 0} demo={false} />
          <ModulePill label="CROWD" active={(state.people_count ?? 0) >= 0} demo={false} />
        </div>
      </div>

      {/* CENTER: Clock */}
      <div className="absolute left-1/2 -translate-x-1/2 text-center">
        <div className="text-[13px] font-mono font-semibold text-primary tabular">{clock.time}</div>
        <div className="text-[9px] font-mono text-muted-foreground">{clock.date}</div>
      </div>

      {/* RIGHT: Actions */}
      <div className="flex items-center gap-2">
        {/* WS status */}
        <div className="flex items-center gap-1.5 text-[9px] font-mono">
          <div className={`w-1.5 h-1.5 rounded-full ${activeCamera ? "bg-status-online animate-pulse" : "bg-muted-foreground"}`} />
          <span className={`uppercase ${activeCamera ? "text-status-online" : "text-muted-foreground"}`}>
            {activeCamera ? "LIVE" : "OFFLINE"}
          </span>
        </div>
        <div className="w-px h-5 bg-border" />

        {/* Notification Toggle */}
        <button
          onClick={onToggleNotifications}
          title={notificationsEnabled ? "Disable Tactical Notifications" : "Enable Tactical Notifications"}
          className={`flex items-center gap-1.5 px-2 py-1 border text-[9px] font-mono uppercase transition-all ${
            notificationsEnabled
              ? "border-primary/50 bg-primary/10 text-primary hover:bg-primary/20"
              : "border-border text-muted-foreground hover:text-foreground"
          }`}
        >
          {notificationsEnabled ? <Bell size={12} /> : <BellOff size={12} />}
          <span>{notificationsEnabled ? "ALERTS: ON" : "ALERTS: OFF"}</span>
        </button>

        <div className="w-px h-5 bg-border" />

        {/* Alert counter */}
        <button
          onClick={onOpenAlertHistory}
          className={`flex items-center gap-1 px-2 py-1 border text-[9px] font-mono uppercase transition-all ${
            alertCount > 0
              ? "border-status-alert/50 bg-status-alert/10 text-status-alert hover:bg-status-alert/20"
              : "border-border text-muted-foreground hover:text-foreground"
          }`}
        >
          <AlertTriangle size={12} />
          <span>{alertCount}</span>
        </button>

        {/* Report Download */}
        <button
          onClick={handleDownloadReport}
          disabled={isDownloading || !activeCamera}
          className="flex items-center gap-1.5 px-2 py-1 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:border-primary/50 hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          <Download size={12} />
          {isDownloading ? "GENERATING..." : "REPORT"}
        </button>

        {/* Add Feed — primary */}
        <button
          onClick={onOpenAddFeed}
          className="flex items-center gap-1.5 px-2 py-1 border border-primary/50 bg-primary/15 text-[9px] font-mono uppercase text-primary hover:bg-primary/25 hover:border-primary/80 transition-all"
        >
          <Plus size={12} />
          ADD FEED
        </button>

        {/* Settings */}
        <button
          onClick={onOpenSettings}
          className="flex items-center gap-1.5 px-2 py-1 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:border-primary/50 hover:text-foreground transition-all"
        >
          ⚙ SETTINGS
        </button>
      </div>
    </header>
  );
}
