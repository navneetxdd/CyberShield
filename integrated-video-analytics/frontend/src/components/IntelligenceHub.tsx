import { useState, useEffect } from "react";
import { CyberShieldState } from "../pages/Index";

type TabKey = "faces" | "plates" | "vehicles" | "crowd";

function ConfidenceBar({ value }: { value: number }) {
  const getColorClass = (v: number) => {
    if (v > 0.95) return "bg-status-alert";
    if (v > 0.9) return "bg-primary";
    if (v > 0.8) return "bg-secondary";
    return "bg-muted-foreground";
  };
  return (
    <div className="w-full bg-muted/10 h-1 mt-1 overflow-hidden relative">
      <div
        className={`h-full transition-all duration-700 ${getColorClass(value)} shadow-[0_0_6px_currentColor]`}
        style={{ width: `${Math.min(100, value * 100)}%` }}
      />
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    STOLEN: "bg-status-alert/20 border-status-alert/50 text-status-alert",
    INTERCEPT_ORDER: "bg-status-alert/20 border-status-alert/50 text-status-alert",
    FLAGGED_INTEL: "bg-status-warning/20 border-status-warning/50 text-status-warning",
    ANPR_ALERT: "bg-status-alert/20 border-status-alert/50 text-status-alert",
    FOLLOW_LOG: "bg-secondary/20 border-secondary/50 text-secondary",
    CLEARED: "bg-status-online/20 border-status-online/50 text-status-online",
  };
  const cls = colorMap[status] || "bg-muted/20 border-border text-muted-foreground";
  return (
    <span className={`text-[8px] font-mono font-bold uppercase tracking-widest px-1 py-0.5 border ${cls}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function FaceCard({ detection, onClick }: { detection: any; onClick?: () => void }) {
  const isThreat = detection.watchlist_hit;
  const isArmed = detection.is_armed;
  const confidence = detection.confidence ?? 0.85;
  return (
    <div 
      onClick={onClick}
      className={`group relative border p-2.5 cursor-pointer transition-all duration-300 animate-card-slide ${isArmed ? "border-status-alert bg-status-alert/10 shadow-[0_0_15px_rgba(239,68,68,0.2)]" : isThreat ? "border-status-alert/60 bg-status-alert/5" : "border-border/40 bg-surface hover:border-primary/50 hover:bg-primary/5"}`}
    >
      {(isThreat || isArmed) && <div className={`absolute top-0 left-0 w-full h-px ${isArmed ? "bg-status-alert animate-pulse" : "bg-status-alert"} shadow-[0_0_8px_hsl(var(--status-alert))]`} />}
      <div className="flex justify-between items-center mb-1.5">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${isThreat || isArmed ? "bg-status-alert animate-ping" : "bg-secondary"}`} />
          <span className={`text-[9px] font-mono tracking-widest font-bold ${isThreat || isArmed ? "text-status-alert" : "text-secondary"}`}>
            {isArmed ? "⚠ ARMED INDIVIDUAL" : isThreat ? "⚠ WATCHLIST MATCH" : "FACE_DETECT"}
          </span>
        </div>
        <span className="text-[8px] font-mono text-muted-foreground">{detection.time}</span>
      </div>
      <div className={`text-[12px] font-mono font-bold truncate ${isThreat || isArmed ? "text-status-alert" : "text-foreground"}`}>
        {detection.identity || "ANONYMOUS SUBJECT"}
      </div>
      <div className="grid grid-cols-2 gap-1.5 mt-1.5 text-[9px] font-mono text-muted-foreground">
        <div><span className="text-primary/50">SEX:</span> {detection.gender || "N/A"}</div>
        <div><span className="text-primary/50">AGE:</span> {detection.age ?? "N/A"}</div>
        <div className="col-span-2 flex items-center gap-1">
          <span className="text-primary/50">BIO-ID:</span> 
          <span className={`font-bold ${isArmed ? "text-status-alert" : "text-foreground"}`}>{detection.global_id || detection.bio_id || "PENDING..."}</span>
        </div>
        <div><span className="text-primary/50">ZONE:</span> {detection.zone || "N/A"}</div>
        {detection.is_armed !== undefined && (
          <div className={`font-bold ${isArmed ? "text-status-alert" : "text-status-online"}`}>
            WEAPON: {isArmed ? "DETECTED" : "NONE"}
          </div>
        )}
      </div>
      <ConfidenceBar value={confidence} />
      <div className="flex justify-between items-center mt-1">
        <span className="text-[8px] font-mono text-muted-foreground">SCAN_CONF: {(confidence * 100).toFixed(1)}%</span>
        {isArmed ? <StatusBadge status="INTERCEPT_ORDER" /> : detection.risk_level && <StatusBadge status={`RISK_${detection.risk_level}`} />}
      </div>
      {(isArmed || isThreat) && (
        <div className={`mt-1.5 py-0.5 px-1 ${isArmed ? "bg-status-alert text-white" : "bg-status-alert/20 text-status-alert"} border border-status-alert/30 text-[9px] font-mono font-bold animate-pulse text-center`}>
          ▶ {isArmed ? "TACTICAL EMERGENCY: ARMED" : "IMMEDIATE INTERCEPT RECOMMENDED"} ◀
        </div>
      )}
    </div>
  );
}

function PlateCard({ detection, onClick }: { detection: any; onClick?: () => void }) {
  const isThreat = detection.status === "STOLEN" || detection.status === "INTERCEPT_ORDER";
  const confidence = detection.confidence ?? 0.9;
  return (
    <div className={`group relative border p-2.5 transition-all duration-300 animate-card-slide ${isThreat ? "border-status-alert/60 bg-status-alert/5" : "border-border/40 bg-surface hover:border-primary/50"}`}>
      {isThreat && <div className="absolute top-0 left-0 w-full h-px bg-status-alert shadow-[0_0_8px_hsl(var(--status-alert))]" />}
      <div className="flex justify-between items-center mb-1.5">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 ${isThreat ? "bg-status-alert animate-ping" : "bg-primary"}`} />
          <span className={`text-[9px] font-mono tracking-widest font-bold ${isThreat ? "text-status-alert" : "text-primary"}`}>
            {isThreat ? "⚠ ANPR_ALERT" : "ANPR_READ"}
          </span>
        </div>
        <span className="text-[8px] font-mono text-muted-foreground">{detection.time}</span>
      </div>
      <div className={`text-[18px] font-mono font-bold tracking-[0.3em] ${isThreat ? "text-status-alert" : "text-foreground"}`}>
        {detection.plate_text || "--- ---"}
      </div>
      <div className="grid grid-cols-2 gap-1 mt-1.5 text-[9px] font-mono text-muted-foreground">
        <div><span className="text-primary/50">MAKE:</span> {detection.make || detection.vehicle_type || "N/A"}</div>
        <div><span className="text-primary/50">MODEL:</span> {detection.model || "N/A"}</div>
        <div><span className="text-primary/50">COLOR:</span> {detection.color || "N/A"}</div>
        <div><span className="text-primary/50">YEAR:</span> {detection.year || "N/A"}</div>
        {detection.origin && <div className="col-span-2"><span className="text-primary/50">REG:</span> {detection.origin}</div>}
      </div>
      <div className="flex items-center justify-between mt-1.5">
        <ConfidenceBar value={confidence} />
      </div>
      <div className="flex justify-between items-center mt-1">
        <span className="text-[8px] font-mono text-muted-foreground">OCR_CONF: {(confidence * 100).toFixed(1)}%</span>
        {detection.status && <StatusBadge status={detection.status} />}
      </div>
    </div>
  );
}

function VehicleCard({ detection }: { detection: any }) {
  const isThreat = detection.status === "STOLEN" || detection.status === "INTERCEPT_ORDER";
  const confidence = detection.confidence ?? 0.88;
  return (
    <div className={`group relative border p-2.5 transition-all duration-300 animate-card-slide ${isThreat ? "border-status-alert/60 bg-status-alert/5" : "border-border/40 bg-surface hover:border-primary/50"}`}>
      <div className="flex justify-between items-center mb-1.5">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 bg-primary" />
          <span className="text-[9px] font-mono tracking-widest font-bold text-primary">VEHICLE_TRACK</span>
        </div>
        <span className="text-[8px] font-mono text-muted-foreground">{detection.time}</span>
      </div>
      <div className="text-[12px] font-mono font-bold truncate text-foreground">{detection.vehicle_type || "VEHICLE"}</div>
      <div className="grid grid-cols-2 gap-1 mt-1.5 text-[9px] font-mono text-muted-foreground">
        {detection.plate_text && <div><span className="text-primary/50">PLATE:</span> {detection.plate_text}</div>}
        {detection.color && <div><span className="text-primary/50">COLOR:</span> {detection.color}</div>}
        <div><span className="text-primary/50">TRK_ID:</span> #{detection.tracker_id}</div>
        <div><span className="text-primary/50">CONF:</span> {(confidence * 100).toFixed(1)}%</div>
      </div>
      <ConfidenceBar value={confidence} />
      {detection.status && (
        <div className="mt-1.5"><StatusBadge status={detection.status} /></div>
      )}
    </div>
  );
}

function CrowdPanel({ state }: { state: CyberShieldState }) {
  const genders = state.gender_stats || {};
  const total = Object.values(genders).reduce((a: number, b: any) => a + (b as number), 0) || 1;
  const crowdLevel = state.crowd_density || "LOW";
  const crowdColor = crowdLevel === "High" ? "text-status-alert" : crowdLevel === "Medium" ? "text-status-warning" : "text-status-online";

  return (
    <div className="p-2 space-y-3">
      {/* Module: People Counting */}
      <div className="border border-border/40 p-2 bg-surface">
        <div className="text-[10px] font-mono tracking-widest uppercase text-primary mb-2">◉ MODULE 4: People Counting & Gender Classification</div>
        <div className="grid grid-cols-2 gap-2">
          <div className="text-center">
            <div className="text-[28px] font-mono font-bold text-foreground">{state.people_count}</div>
            <div className="text-[9px] font-mono text-muted-foreground uppercase">Persons Detected</div>
          </div>
          <div className="text-center">
            <div className={`text-[20px] font-mono font-bold uppercase ${crowdColor}`}>{crowdLevel}</div>
            <div className="text-[9px] font-mono text-muted-foreground uppercase">Crowd Density</div>
          </div>
        </div>
      </div>

      {/* Gender Distribution */}
      <div className="border border-border/40 p-2 bg-surface">
        <div className="text-[9px] font-mono text-muted-foreground uppercase mb-2 tracking-widest">Gender Analytics</div>
        {Object.entries(genders).map(([gender, count]: [string, any]) => {
          const pct = Math.round((count / total) * 100);
          const gColor = gender === "Male" ? "bg-primary" : gender === "Female" ? "bg-secondary" : "bg-muted-foreground";
          return (
            <div key={gender} className="flex items-center gap-2 mb-2">
              <div className={`w-2 h-2 rounded-full ${gColor}`} />
              <span className="text-[10px] font-mono text-muted-foreground w-14">{gender}</span>
              <div className="flex-1 bg-muted/10 h-2 overflow-hidden">
                <div className={`h-full ${gColor} transition-all duration-700`} style={{ width: `${pct}%` }} />
              </div>
              <span className="text-[10px] font-mono text-foreground font-bold w-10 text-right">{count} ({pct}%)</span>
            </div>
          );
        })}
      </div>

      {/* Age demographics hint */}
      <div className="border border-border/40 p-2 bg-surface">
        <div className="text-[9px] font-mono text-muted-foreground uppercase mb-2 tracking-widest">Biometric Demographics</div>
        <div className="grid grid-cols-3 gap-1 text-center text-[9px] font-mono">
          {[["18–25", "22%"], ["26–40", "45%"], ["41–60", "28%"], ["60+", "5%"], ["FRS Rate", "91.2%"], ["Avg Conf", "93.4%"]].map(([lbl, val]) => (
            <div key={lbl} className="border border-border/20 p-1">
              <div className="text-foreground font-bold text-[11px]">{val}</div>
              <div className="text-muted-foreground">{lbl}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

interface IntelligenceHubProps {
  state: CyberShieldState;
  onFaceClick?: (face: any) => void;
  onPlateClick?: (plate: any) => void;
}

export function IntelligenceHub({ state, onFaceClick, onPlateClick }: IntelligenceHubProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("faces");

  const faces = state.recent_faces || [];
  const plates = state.recent_plates || [];
  const vehicles = state.recent_vehicles || [];
  const logs = state.event_logs || [];
  const processedCount = state.vehicle_count + state.people_count;
  const watchlistHits = faces.filter((f: any) => f.watchlist_hit).length;

  const tabs: { key: TabKey; label: string; icon: string; count: number }[] = [
    { key: "faces", label: "FRS", icon: "◉", count: faces.length },
    { key: "plates", label: "ANPR", icon: "◻", count: plates.length },
    { key: "vehicles", label: "VEH", icon: "▣", count: vehicles.length },
    { key: "crowd", label: "CROWD", icon: "⬡", count: state.people_count },
  ];

  return (
    <aside className="col-span-3 border border-border bg-panel flex flex-col min-h-0">
      {/* Header */}
      <div className="p-2 border-b border-border flex justify-between items-center shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-secondary glow-indigo animate-pulse" />
          <h2 className="text-[11px] font-mono font-bold tracking-[0.1em] uppercase text-foreground">INTEL HUB</h2>
        </div>
        <div className="flex items-center gap-2">
          {watchlistHits > 0 && (
            <span className="text-[9px] font-mono text-status-alert font-bold animate-pulse">
              ⚠ {watchlistHits} WL-HIT{watchlistHits > 1 ? "S" : ""}
            </span>
          )}
          <div className="w-px h-3 bg-border" />
          <span className="text-[9px] font-mono text-secondary font-bold">● LIVE</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border shrink-0">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 px-1 py-1.5 text-[9px] font-mono tracking-wider uppercase transition-all border-b-2 ${
              activeTab === tab.key
                ? "border-primary text-primary bg-primary/5"
                : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/5"
            }`}
          >
            <span className="mr-0.5">{tab.icon}</span>
            {tab.label}
            <span className="ml-0.5 text-[8px] tabular">({tab.count})</span>
          </button>
        ))}
      </div>

      {/* Detection List */}
      <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5 min-h-0">
        {activeTab === "crowd" ? (
          <CrowdPanel state={state} />
        ) : activeTab === "faces" ? (
          faces.length === 0
            ? <div className="text-[10px] font-mono text-muted-foreground/50 text-center p-4">NO_FACE_DATA — Awaiting stream</div>
            : faces.map((d: any, idx: number) => <FaceCard key={`face-${idx}`} detection={d} onClick={() => onFaceClick?.(d)} />)
        ) : activeTab === "plates" ? (
          plates.length === 0
            ? <div className="text-[10px] font-mono text-muted-foreground/50 text-center p-4">NO_PLATE_DATA — Awaiting stream</div>
            : plates.map((d: any, idx: number) => <PlateCard key={`plate-${idx}`} detection={d} onClick={() => onPlateClick?.(d)} />)
        ) : (
          vehicles.length === 0
            ? <div className="text-[10px] font-mono text-muted-foreground/50 text-center p-4">NO_VEHICLE_DATA — Awaiting stream</div>
            : vehicles.map((d: any, idx: number) => <VehicleCard key={`veh-${idx}`} detection={d} />)
        )}
      </div>

      {/* Footer — Tactical Terminal Log */}
      <div className="p-2 border-t border-border shrink-0 bg-background/40">
        <div className="flex justify-between items-center text-[9px] font-mono mb-1 tracking-widest uppercase">
          <span className="text-primary/60">CORE_THREAT_LEVEL</span>
          <span className={processedCount > 15 ? "text-status-alert animate-strobe" : processedCount > 8 ? "text-status-warning" : "text-status-online"}>
            {processedCount > 15 ? "CRITICAL" : processedCount > 8 ? "ELEVATED" : "NOMINAL"}
          </span>
        </div>
        <div className="flex gap-0.5 h-1.5 mb-2">
          {Array.from({ length: 40 }).map((_, i) => (
            <div
              key={i}
              className={`flex-1 transition-all duration-500 ${
                processedCount * 2 > i
                  ? i > 30 ? "bg-status-alert shadow-[0_0_5px_hsl(var(--status-alert))]" : i > 15 ? "bg-status-warning" : "bg-primary"
                  : "bg-white/5"
              }`}
            />
          ))}
        </div>
        <div className="h-24 overflow-hidden relative border border-border/20 bg-black/20 p-1.5">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-primary/5 to-transparent animate-scan pointer-events-none" />
          <div className="space-y-0.5">
            {logs.slice(-7).map((log: any, idx: number) => (
              <div key={idx} className="flex gap-2 text-[10px] font-mono leading-tight">
                <span className="text-muted-foreground/40 shrink-0">[{log.time}]</span>
                <span className={`shrink-0 font-bold ${log.type?.includes("TACTICAL") || log.type?.includes("ALERT") || log.type?.includes("BOLO") ? "text-status-alert" : "text-primary/70"}`}>
                  {log.type}:
                </span>
                <span className="text-muted-foreground/80 truncate">{log.detail}</span>
              </div>
            ))}
            {logs.length === 0 && (
              <div className="text-[10px] font-mono text-primary/40">
                [{new Date().toLocaleTimeString()}] SYSTEM_BOOT ... ANALYTICS_CORE_READY
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5 mt-1 px-1 py-0.5 border-t border-border/10">
          <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          <span className="text-[9px] font-mono text-primary/40 uppercase tracking-widest">System_Nominal // AI_Inference_Active</span>
        </div>
      </div>
    </aside>
  );
}
