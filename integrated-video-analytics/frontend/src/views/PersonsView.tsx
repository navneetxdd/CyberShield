import { useState, useEffect, useCallback } from "react";
import { PersonStanding, Search, Camera, Clock } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface FaceRecord {
  id: number;
  camera_id: string;
  tracker_id: number;
  identity: string | null;
  gender: string | null;
  age: number | null;
  watchlist_hit: number;
  first_seen: string;
  last_seen: string;
}

export function PersonsView() {
  const [records, setRecords] = useState<FaceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const fetchRecords = useCallback(async () => {
    try {
      const data = await apiFetch("/api/records/faces?limit=200") as any;
      setRecords(data?.records || []);
    } catch {
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRecords();
    const interval = setInterval(fetchRecords, 8000);
    return () => clearInterval(interval);
  }, [fetchRecords]);

  const filtered = records.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (r.identity || "").toLowerCase().includes(q) ||
      r.camera_id.toLowerCase().includes(q) ||
      String(r.tracker_id).includes(q)
    );
  });

  const watchlistHits = records.filter(r => r.watchlist_hit === 1).length;
  const uniqueCams = new Set(records.map(r => r.camera_id)).size;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-panel shrink-0">
        <div className="flex items-center gap-2">
          <PersonStanding size={16} className="text-primary" />
          <span className="text-[11px] font-mono font-semibold text-primary uppercase tracking-widest">PERSONS REGISTRY</span>
        </div>
        <div className="flex items-center gap-2">
          {watchlistHits > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-1 border border-status-alert/40 bg-status-alert/10 text-[9px] font-mono text-status-alert uppercase">
              ⚠ {watchlistHits} WATCHLIST HIT{watchlistHits !== 1 ? "S" : ""}
            </div>
          )}
          <div className="text-[9px] font-mono text-muted-foreground">{records.length} TOTAL</div>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-4 gap-px bg-border shrink-0">
        {[
          { label: "PERSONS DETECTED", value: records.length, color: "text-primary" },
          { label: "WATCHLIST HITS", value: watchlistHits, color: watchlistHits > 0 ? "text-status-alert" : "text-status-online" },
          { label: "CAMERAS ACTIVE", value: uniqueCams, color: "text-primary" },
          { label: "IDENTIFIED", value: records.filter(r => r.identity).length, color: "text-status-online" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-panel px-4 py-3">
            <div className="text-[8px] font-mono text-muted-foreground uppercase tracking-widest mb-1">{label}</div>
            <div className={`text-[20px] font-mono font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Search */}
      <div className="px-4 py-2 border-b border-border bg-panel shrink-0">
        <div className="flex items-center gap-2 border border-border px-2 py-1">
          <Search size={12} className="text-muted-foreground shrink-0" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="SEARCH BY IDENTITY, CAMERA, TRACKER ID..."
            className="flex-1 text-[9px] font-mono bg-transparent text-foreground placeholder:text-muted-foreground/40 focus:outline-none uppercase"
          />
          {search && (
            <button onClick={() => setSearch("")} className="text-muted-foreground hover:text-foreground text-[9px] font-mono">✕</button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-[10px] font-mono text-muted-foreground uppercase animate-pulse">LOADING PERSON RECORDS...</div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <PersonStanding size={32} className="text-muted-foreground/30" />
            <div className="text-[11px] font-mono text-muted-foreground uppercase">
              {records.length === 0 ? "NO PERSONS DETECTED YET" : "NO MATCHING RECORDS"}
            </div>
            <div className="text-[9px] font-mono text-muted-foreground/50 text-center max-w-xs">
              {records.length === 0
                ? "Person records populate automatically as individuals are detected in active camera feeds."
                : "Try adjusting your search query."}
            </div>
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-panel border-b border-border">
              <tr>
                {["TRACKER", "IDENTITY", "CAMERA", "GENDER", "AGE", "WATCHLIST", "FIRST SEEN", "LAST SEEN"].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-[8px] font-mono text-muted-foreground uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                <tr key={r.id} className={`border-b border-border/40 hover:bg-primary/5 transition-colors ${r.watchlist_hit ? "bg-status-alert/5" : i % 2 === 0 ? "" : "bg-surface/30"}`}>
                  <td className="px-3 py-2 text-[9px] font-mono text-muted-foreground">#{r.tracker_id}</td>
                  <td className="px-3 py-2 text-[9px] font-mono font-semibold">
                    {r.identity ? (
                      <span className={r.watchlist_hit ? "text-status-alert" : "text-foreground"}>{r.identity}</span>
                    ) : (
                      <span className="text-muted-foreground/50">UNIDENTIFIED</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 text-[9px] font-mono text-muted-foreground">
                      <Camera size={9} /> {r.camera_id}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-[9px] font-mono text-muted-foreground">{r.gender || "—"}</td>
                  <td className="px-3 py-2 text-[9px] font-mono text-muted-foreground">{r.age ?? "—"}</td>
                  <td className="px-3 py-2">
                    {r.watchlist_hit ? (
                      <span className="text-[8px] font-mono text-status-alert border border-status-alert/40 px-1.5 py-0.5 uppercase">⚠ MATCH</span>
                    ) : (
                      <span className="text-[8px] font-mono text-status-online/60">CLEAR</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 text-[8px] font-mono text-muted-foreground">
                      <Clock size={9} /> {new Date(r.first_seen).toLocaleTimeString()}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 text-[8px] font-mono text-muted-foreground">
                      <Clock size={9} /> {new Date(r.last_seen).toLocaleTimeString()}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
