import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { UserSearch, Star, StarOff, RefreshCw, X, Clock, Camera, Shield } from "lucide-react";

interface Person {
  global_id: string;
  display_name: string | null;
  watchlist_flag: number;
  watchlist_meta: Record<string, any>;
  last_seen_ts: string;
  last_seen_camera: string;
  cameras_visited: number;
  tracklet_count: number;
}

interface TimelineEntry {
  tracklet_id: string;
  camera_id: string;
  start_ts: string;
  end_ts: string;
  frame_count: number;
}

interface MovementEvent {
  global_id: string;
  from_camera: string;
  to_camera: string;
  timestamp: string;
  display_name: string;
}

function PersonDetailModal({
  person,
  onClose,
  onWatchlistToggle,
}: {
  person: Person;
  onClose: () => void;
  onWatchlistToggle: () => void;
}) {
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [name, setName] = useState(person.watchlist_meta?.display_name || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiFetch(`/api/persons/${person.global_id}/timeline`)
      .then((d: any) => setTimeline(d?.timeline || []))
      .catch(() => {});
  }, [person.global_id]);

  const toggleWatchlist = async () => {
    setSaving(true);
    try {
      const flag = !person.watchlist_flag;
      await apiFetch(`/api/persons/${person.global_id}/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flag, display_name: name }),
      });
      onWatchlistToggle();
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  };

  const snapshotUrl = `/api/persons/${person.global_id}/snapshot.jpg`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-panel border border-border rounded-lg w-[680px] max-h-[90vh] overflow-auto p-6 relative">
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-muted-foreground hover:text-foreground"
        >
          <X size={16} />
        </button>

        <div className="flex gap-5 mb-6">
          {/* Snapshot */}
          <div className="shrink-0">
            <img
              src={snapshotUrl}
              alt="face"
              className="w-28 h-28 object-cover rounded border border-border"
              onError={(e) => {
                (e.target as HTMLImageElement).src = "";
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          </div>

          {/* Identity info */}
          <div className="flex-1">
            <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">Global ID</div>
            <div className="text-[13px] font-mono text-primary mb-2">{person.global_id}</div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">Last seen</div>
            <div className="text-[12px] font-mono mb-2">
              {person.last_seen_camera} · {person.last_seen_ts?.slice(0, 19) || "—"}
            </div>
            <div className="flex gap-2 items-center mt-3">
              <input
                className="bg-background border border-border rounded px-2 py-1 text-[11px] font-mono w-40"
                placeholder="Label / alias"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <button
                onClick={toggleWatchlist}
                disabled={saving}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-[10px] font-mono uppercase tracking-wider transition-colors ${
                  person.watchlist_flag
                    ? "bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30"
                    : "bg-primary/10 text-primary hover:bg-primary/20"
                }`}
              >
                {person.watchlist_flag ? <StarOff size={12} /> : <Star size={12} />}
                {person.watchlist_flag ? "Remove Watchlist" : "Add to Watchlist"}
              </button>
            </div>
          </div>
        </div>

        {/* Movement timeline */}
        <div>
          <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-3">
            Camera Movement Timeline
          </div>
          {timeline.length === 0 ? (
            <div className="text-[11px] text-muted-foreground">No movement data yet.</div>
          ) : (
            <div className="relative flex items-center gap-0">
              {timeline.map((entry, i) => (
                <div key={entry.tracklet_id} className="flex items-center">
                  <div className="flex flex-col items-center">
                    <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary flex items-center justify-center">
                      <Camera size={12} className="text-primary" />
                    </div>
                    <div className="text-[9px] font-mono text-primary mt-1 max-w-[80px] text-center truncate">
                      {entry.camera_id}
                    </div>
                    <div className="text-[8px] font-mono text-muted-foreground text-center">
                      {entry.start_ts?.slice(11, 19) || ""}
                    </div>
                  </div>
                  {i < timeline.length - 1 && (
                    <div className="h-0.5 w-10 bg-primary/30 mx-1" />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function PersonsView() {
  const [persons, setPersons] = useState<Person[]>([]);
  const [movements, setMovements] = useState<MovementEvent[]>([]);
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [pData, mData] = await Promise.all([
        apiFetch(`/api/persons?watchlist_only=${watchlistOnly}`) as Promise<any>,
        apiFetch("/api/persons/movements") as Promise<any>,
      ]);
      setPersons(pData?.persons || []);
      setMovements(mData?.movements || []);
    } catch {
      /* offline */
    } finally {
      setLoading(false);
    }
  }, [watchlistOnly]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const watchlisted = persons.filter((p) => p.watchlist_flag);
  const helmetViolations = 0; // populated from helmet events in future iteration

  return (
    <div className="h-full flex overflow-hidden">
      {/* Main panel */}
      <div className="flex-1 flex flex-col overflow-hidden p-4">
        {/* KPI row */}
        <div className="grid grid-cols-4 gap-3 mb-4">
          {[
            { label: "TRACKED", value: persons.length },
            { label: "WATCHLISTED", value: watchlisted.length },
            { label: "CAMERAS ACTIVE", value: new Set(persons.map((p) => p.last_seen_camera).filter(Boolean)).size },
            { label: "CROSS-CAMERA", value: movements.length },
          ].map(({ label, value }) => (
            <div key={label} className="bg-panel border border-border rounded p-3">
              <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest mb-1">{label}</div>
              <div className="text-[22px] font-mono text-primary font-bold">{value}</div>
            </div>
          ))}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3 mb-3">
          <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-widest">PERSONS</span>
          <label className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={watchlistOnly}
              onChange={(e) => setWatchlistOnly(e.target.checked)}
              className="rounded"
            />
            Watchlist only
          </label>
          <button
            onClick={fetchData}
            disabled={loading}
            className="ml-auto flex items-center gap-1 text-[10px] font-mono text-muted-foreground hover:text-foreground"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto border border-border rounded">
          <table className="w-full text-[11px] font-mono">
            <thead className="sticky top-0 bg-panel border-b border-border">
              <tr>
                <th className="text-left px-3 py-2 text-muted-foreground font-normal uppercase tracking-wider text-[9px] w-16">Snap</th>
                <th className="text-left px-3 py-2 text-muted-foreground font-normal uppercase tracking-wider text-[9px]">Global ID</th>
                <th className="text-left px-3 py-2 text-muted-foreground font-normal uppercase tracking-wider text-[9px]">Last Camera</th>
                <th className="text-left px-3 py-2 text-muted-foreground font-normal uppercase tracking-wider text-[9px]">Last Seen</th>
                <th className="text-left px-3 py-2 text-muted-foreground font-normal uppercase tracking-wider text-[9px]">Cameras</th>
                <th className="text-left px-3 py-2 text-muted-foreground font-normal uppercase tracking-wider text-[9px]">WL</th>
              </tr>
            </thead>
            <tbody>
              {persons.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-muted-foreground">
                    {loading ? "Loading..." : "No persons tracked yet. Assign video feeds and enable face detection."}
                  </td>
                </tr>
              ) : (
                persons.map((p) => (
                  <tr
                    key={p.global_id}
                    onClick={() => setSelectedPerson(p)}
                    className={`border-b border-border/50 cursor-pointer hover:bg-border/30 transition-colors ${
                      p.watchlist_flag ? "bg-yellow-500/5" : ""
                    }`}
                  >
                    <td className="px-3 py-2">
                      <img
                        src={`/api/persons/${p.global_id}/snapshot.jpg`}
                        alt=""
                        className="w-10 h-10 object-cover rounded border border-border"
                        onError={(e) => { (e.target as HTMLImageElement).style.opacity = "0"; }}
                      />
                    </td>
                    <td className="px-3 py-2 text-primary">
                      {p.display_name || p.watchlist_meta?.display_name || p.global_id}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{p.last_seen_camera || "—"}</td>
                    <td className="px-3 py-2 text-muted-foreground">{p.last_seen_ts?.slice(0, 19) || "—"}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 text-primary">
                        <Camera size={10} /> {p.cameras_visited}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      {p.watchlist_flag ? (
                        <Shield size={13} className="text-yellow-400" />
                      ) : (
                        <span className="text-muted-foreground/40">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right panel: movement feed */}
      <div className="w-72 border-l border-border flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <Clock size={13} className="text-muted-foreground" />
          <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">
            Cross-Camera Movements
          </span>
        </div>
        <div className="flex-1 overflow-auto">
          {movements.length === 0 ? (
            <div className="px-4 py-6 text-[11px] text-muted-foreground text-center">
              No cross-camera movements yet.
            </div>
          ) : (
            movements.slice(0, 30).map((m, i) => (
              <div key={i} className="px-4 py-2.5 border-b border-border/50">
                <div className="text-[10px] font-mono text-primary mb-0.5">
                  {m.display_name || m.global_id}
                </div>
                <div className="text-[10px] font-mono text-muted-foreground flex items-center gap-1.5">
                  <span>{m.from_camera}</span>
                  <span className="text-primary">→</span>
                  <span>{m.to_camera}</span>
                </div>
                <div className="text-[9px] font-mono text-muted-foreground/60 mt-0.5">
                  {m.timestamp?.slice(0, 19) || ""}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {selectedPerson && (
        <PersonDetailModal
          person={selectedPerson}
          onClose={() => setSelectedPerson(null)}
          onWatchlistToggle={() => {
            fetchData();
            setSelectedPerson(null);
          }}
        />
      )}
    </div>
  );
}
