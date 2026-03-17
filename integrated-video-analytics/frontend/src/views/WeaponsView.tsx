import { useState, useEffect, useCallback } from "react";
import { ShieldAlert, AlertTriangle, Clock, Camera } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface WeaponEvent {
  id: number;
  camera_id: string;
  timestamp: string;
  event_type: string;
  detail: string;
}

export function WeaponsView() {
  const [events, setEvents] = useState<WeaponEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchEvents = useCallback(async () => {
    try {
      const data = await apiFetch("/api/events?event_type=weapon&limit=100") as any;
      if (data?.events) {
        setEvents(data.events);
      } else {
        // Fall back to all events and filter weapon-related
        const all = await apiFetch("/api/events?limit=200") as any;
        const weaponEvents = (all?.events || []).filter((e: WeaponEvent) =>
          /weapon|gun|knife|armed|firearm/i.test(e.event_type + " " + (e.detail || ""))
        );
        setEvents(weaponEvents);
      }
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, 10000);
    return () => clearInterval(interval);
  }, [fetchEvents]);

  const threatLevel = events.length === 0 ? "CLEAR" : events.length < 3 ? "ELEVATED" : "CRITICAL";
  const threatColor = threatLevel === "CLEAR" ? "text-status-online" : threatLevel === "ELEVATED" ? "text-status-warning" : "text-status-alert";
  const threatBg = threatLevel === "CLEAR" ? "border-status-online/30 bg-status-online/5" : threatLevel === "ELEVATED" ? "border-status-warning/30 bg-status-warning/5" : "border-status-alert/30 bg-status-alert/5";

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-panel shrink-0">
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} className="text-status-alert" />
          <span className="text-[11px] font-mono font-semibold text-status-alert uppercase tracking-widest">WEAPONS DETECTION</span>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1 border text-[9px] font-mono uppercase ${threatBg} ${threatColor}`}>
          <div className={`w-1.5 h-1.5 rounded-full ${threatLevel !== "CLEAR" ? "animate-pulse" : ""} ${threatLevel === "CLEAR" ? "bg-status-online" : threatLevel === "ELEVATED" ? "bg-status-warning" : "bg-status-alert"}`} />
          THREAT LEVEL: {threatLevel}
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-3 gap-px bg-border shrink-0">
        {[
          { label: "TOTAL INCIDENTS", value: events.length, color: events.length > 0 ? "text-status-alert" : "text-status-online" },
          { label: "CAMERAS AFFECTED", value: new Set(events.map(e => e.camera_id)).size, color: "text-primary" },
          { label: "STATUS", value: threatLevel, color: threatColor },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-panel px-4 py-3">
            <div className="text-[8px] font-mono text-muted-foreground uppercase tracking-widest mb-1">{label}</div>
            <div className={`text-[20px] font-mono font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-[10px] font-mono text-muted-foreground uppercase animate-pulse">SCANNING FEEDS...</div>
          </div>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <div className="w-16 h-16 border border-status-online/30 flex items-center justify-center">
              <ShieldAlert size={28} className="text-status-online/50" />
            </div>
            <div className="text-[11px] font-mono text-status-online uppercase tracking-wider">NO WEAPON EVENTS DETECTED</div>
            <div className="text-[9px] font-mono text-muted-foreground/60 text-center max-w-xs">
              Weapon detection is active. Events will appear here if threats are identified in any camera feed.
            </div>
            <div className="text-[8px] font-mono text-muted-foreground/40 uppercase mt-2">
              WEAPON DETECT: ENABLED · CONFIDENCE THRESHOLD: 0.55
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-[8px] font-mono text-muted-foreground uppercase tracking-widest mb-3">
              INCIDENT LOG — {events.length} EVENT{events.length !== 1 ? "S" : ""}
            </div>
            {events.map((event) => (
              <div key={event.id} className="border border-status-alert/30 bg-status-alert/5 p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={12} className="text-status-alert" />
                    <span className="text-[10px] font-mono text-status-alert uppercase font-bold">{event.event_type}</span>
                  </div>
                  <span className="text-[8px] font-mono text-muted-foreground">#{event.id}</span>
                </div>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1 text-[9px] font-mono text-muted-foreground">
                    <Camera size={10} /> {event.camera_id}
                  </div>
                  <div className="flex items-center gap-1 text-[9px] font-mono text-muted-foreground">
                    <Clock size={10} /> {new Date(event.timestamp).toLocaleTimeString()}
                  </div>
                </div>
                {event.detail && (
                  <div className="text-[9px] font-mono text-foreground/70 pl-1 border-l border-status-alert/30">
                    {event.detail}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
