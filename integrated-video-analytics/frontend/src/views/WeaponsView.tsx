import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { ShieldAlert, CheckCheck, RefreshCw } from "lucide-react";

interface WeaponEvent {
  id: number;
  camera_id: string;
  timestamp: string;
  weapon_type: string;
  confidence: number;
  bounding_box: string | null;
  acknowledged: number;
  acknowledged_at: string | null;
}

interface WeaponSummary {
  total_weapon_events: number;
  unacknowledged_count: number;
  weapon_breakdown: Record<string, number>;
}

const CONFIDENCE_COLOR = (conf: number) =>
  conf >= 0.85 ? "text-red-400" : conf >= 0.70 ? "text-orange-400" : "text-yellow-400";

export function WeaponsView() {
  const [events, setEvents] = useState<WeaponEvent[]>([]);
  const [summary, setSummary] = useState<WeaponSummary | null>(null);
  const [unacknowledgedOnly, setUnacknowledgedOnly] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [eventsData, summaryData] = await Promise.all([
        apiFetch(`/api/weapons/events?limit=100&unacknowledged_only=${unacknowledgedOnly}`) as Promise<any>,
        apiFetch("/api/weapons/summary") as Promise<any>,
      ]);
      setEvents(eventsData?.events || []);
      setSummary(summaryData || null);
    } catch {
      /* offline */
    } finally {
      setLoading(false);
    }
  }, [unacknowledgedOnly]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const acknowledge = async (id: number) => {
    try {
      await apiFetch(`/api/weapons/acknowledge/${id}`, { method: "POST" });
      fetchData();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="h-full overflow-auto bg-background p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert size={20} className="text-red-500" />
          <span className="text-[13px] font-mono font-bold uppercase tracking-widest text-red-400">
            Weapon Detection
          </span>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground border border-border px-2 py-1 transition-colors"
        >
          <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          REFRESH
        </button>
      </div>

      {/* Summary KPIs */}
      {summary && (
        <div className="grid grid-cols-3 gap-2">
          <div className="border border-border bg-panel p-3 text-center">
            <div className="text-[24px] font-mono font-bold text-red-400">
              {summary.total_weapon_events}
            </div>
            <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest">
              Total Detections
            </div>
          </div>
          <div className="border border-red-500/40 bg-panel p-3 text-center">
            <div className="text-[24px] font-mono font-bold text-red-500">
              {summary.unacknowledged_count}
            </div>
            <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest">
              Unacknowledged
            </div>
          </div>
          <div className="border border-border bg-panel p-3 text-center">
            <div className="text-[24px] font-mono font-bold text-orange-400">
              {Object.keys(summary.weapon_breakdown).length}
            </div>
            <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest">
              Weapon Types
            </div>
          </div>
        </div>
      )}

      {/* Type breakdown */}
      {summary && Object.keys(summary.weapon_breakdown).length > 0 && (
        <div className="border border-border bg-panel p-3">
          <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest mb-2">
            Weapon Type Breakdown
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(summary.weapon_breakdown).map(([type, count]) => (
              <div
                key={type}
                className="border border-red-500/30 bg-red-500/5 px-2 py-1 flex items-center gap-1.5"
              >
                <span className="text-[10px] font-mono text-red-400 font-bold">{type}</span>
                <span className="text-[9px] font-mono text-muted-foreground">×{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter row */}
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={unacknowledgedOnly}
            onChange={(e) => setUnacknowledgedOnly(e.target.checked)}
            className="accent-red-500"
          />
          <span className="text-[10px] font-mono text-muted-foreground uppercase">
            Unacknowledged only
          </span>
        </label>
        <span className="text-[10px] font-mono text-muted-foreground/40">
          {events.length} record{events.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Events table */}
      <div className="border border-border bg-panel overflow-hidden">
        <div className="grid grid-cols-[1fr_1.5fr_1fr_1fr_auto] gap-px bg-border text-[9px] font-mono uppercase tracking-widest text-muted-foreground px-3 py-1.5 bg-panel">
          <span>Timestamp</span>
          <span>Weapon Type</span>
          <span>Confidence</span>
          <span>Camera</span>
          <span>Action</span>
        </div>
        {events.length === 0 ? (
          <div className="text-center text-[11px] font-mono text-muted-foreground py-10">
            {unacknowledgedOnly ? "No unacknowledged events" : "No weapon events recorded"}
          </div>
        ) : (
          <div className="divide-y divide-border/30 max-h-[500px] overflow-y-auto">
            {events.map((evt) => (
              <div
                key={evt.id}
                className={`grid grid-cols-[1fr_1.5fr_1fr_1fr_auto] gap-px items-center px-3 py-2 text-[10px] font-mono transition-colors ${
                  evt.acknowledged
                    ? "opacity-50 bg-panel"
                    : "bg-red-500/5 hover:bg-red-500/10"
                }`}
              >
                <span className="text-muted-foreground truncate">
                  {evt.timestamp?.slice(0, 19).replace("T", " ")}
                </span>
                <span className="font-bold text-red-400 uppercase">{evt.weapon_type}</span>
                <span className={CONFIDENCE_COLOR(evt.confidence)}>
                  {(evt.confidence * 100).toFixed(1)}%
                </span>
                <span className="text-muted-foreground truncate">{evt.camera_id}</span>
                <div className="flex items-center gap-1 pl-2">
                  {!evt.acknowledged ? (
                    <button
                      onClick={() => acknowledge(evt.id)}
                      className="flex items-center gap-1 text-[9px] font-mono text-green-400 border border-green-500/30 hover:bg-green-500/10 px-1.5 py-0.5 transition-colors"
                    >
                      <CheckCheck size={10} />
                      ACK
                    </button>
                  ) : (
                    <span className="text-[9px] font-mono text-muted-foreground/40">ACKED</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
