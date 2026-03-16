import { useState, useEffect } from "react";
import { Users, AlertTriangle, Shield, Camera, RefreshCw } from "lucide-react";
import { CyberShieldState } from "../pages/Index";
import { CrowdDensityGauge } from "../components/CrowdDensityGauge";
import { apiFetch } from "../lib/api";

interface WatchlistViewProps {
  state: CyberShieldState;
  activeCamera: string;
}

interface Subject { name: string; enrolled_at?: string; }
interface WatchlistEntry { identity: string; updated_at?: number; }
interface TrackedPerson {
  global_id: string;
  display_name: string;
  watchlist_flag: number;
  watchlist_meta: Record<string, any>;
  last_seen_ts: string;
  last_seen_camera: string;
  cameras_visited: number;
}

export function WatchlistView({ state, activeCamera }: WatchlistViewProps) {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [enrollName, setEnrollName] = useState("");
  const [enrollFile, setEnrollFile] = useState<File | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [trackedPersons, setTrackedPersons] = useState<TrackedPerson[]>([]);
  const [trackedLoading, setTrackedLoading] = useState(false);

  const loadTrackedPersons = async () => {
    setTrackedLoading(true);
    try {
      const data = await apiFetch<{ persons: TrackedPerson[] }>("/api/persons?watchlist_only=true");
      setTrackedPersons(data?.persons || []);
    } catch { setTrackedPersons([]); }
    setTrackedLoading(false);
  };

  const removeFromTrackedWatchlist = async (globalId: string) => {
    try {
      await apiFetch(`/api/persons/${globalId}/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flag: false }),
      });
      setTrackedPersons(p => p.filter(x => x.global_id !== globalId));
    } catch { /* ignore */ }
  };

  const recentlyDetected = (name: string) => {
    return state.event_logs?.some(e => e.detail?.includes(name) && e.type?.includes("Watchlist"));
  };

  const loadSubjects = async () => {
    setLoading(true);
    try {
      const data = await apiFetch<{ entries?: WatchlistEntry[] }>("/api/watchlist/files");
      const mapped = (data?.entries || []).map((entry) => ({
        name: entry.identity,
        enrolled_at: entry.updated_at ? new Date(entry.updated_at * 1000).toISOString() : undefined,
      }));
      setSubjects(mapped);
    } catch { setSubjects([]); }
    setLoading(false);
  };

  useEffect(() => { loadSubjects(); loadTrackedPersons(); }, []);

  // Refresh tracked persons every 5s so newly watchlisted persons appear automatically
  useEffect(() => {
    const iv = setInterval(loadTrackedPersons, 5000);
    return () => clearInterval(iv);
  }, []);

  const handleEnroll = async () => {
    if (!enrollFile || !enrollName.trim()) return;
    if (!/^[A-Za-z0-9_-]+$/.test(enrollName)) {
      alert("Name must be letters, numbers, hyphens, underscores only."); return;
    }
    setEnrolling(true);
    try {
      const form = new FormData();
      form.append("name", enrollName);
      form.append("file", enrollFile);
      const { apiUpload } = await import("../lib/api");
      await apiUpload("/api/watchlist/files", form);
      const r = { ok: true };
      if (r.ok) { await loadSubjects(); setEnrollOpen(false); setEnrollName(""); setEnrollFile(null); }
      else alert("Enrollment failed.");
    } catch {
      alert("Enrollment failed.");
    }
    setEnrolling(false);
  };

  const handleRemove = async (name: string) => {
    if (!confirm(`Remove ${name} from watchlist? Cannot be undone.`)) return;
    try { await apiFetch(`/api/watchlist/files/${encodeURIComponent(name)}`, { method: "DELETE" }); } catch { /* ignore */ }
    setSubjects(p => p.filter(s => s.name !== name));
  };

  const filtered = subjects.filter(s => s.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="h-full flex overflow-hidden">
      {/* LEFT: Enrolled Subjects (60%) */}
      <div className="flex-[3] flex flex-col border-r border-border overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-panel shrink-0">
          <span className="text-[10px] font-mono text-foreground uppercase tracking-wider">
            WATCHLIST // {subjects.length} SUBJECTS ENROLLED
          </span>
          <button onClick={() => setEnrollOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase hover:bg-primary/25 transition-all">
            + ENROLL SUBJECT
          </button>
        </div>

        <div className="px-3 py-2 border-b border-border shrink-0">
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="SEARCH SUBJECT..."
            className="w-full text-[11px] font-mono bg-background border border-border px-3 py-1.5 text-foreground placeholder:text-muted-foreground/50" />
        </div>

        {/* Subject Grid */}
        <div className="flex-1 overflow-y-auto p-3">
          {loading ? (
            <div className="grid grid-cols-3 gap-2">
              {[1,2,3].map(i => <div key={i} className="skeleton h-24 border border-border" />)}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <Users size={40} className="text-muted-foreground/40" />
              <div className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">NO SUBJECTS ENROLLED</div>
              <div className="text-[10px] font-sans text-muted-foreground/60 text-center max-w-xs">
                Enroll a subject to enable facial recognition matching.
              </div>
              <button onClick={() => setEnrollOpen(true)}
                className="px-4 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase tracking-wider hover:bg-primary/25 transition-all">
                + ENROLL FIRST SUBJECT
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {filtered.map(s => {
                const detected = recentlyDetected(s.name);
                return (
                  <div key={s.name}
                    className={`border p-3 flex flex-col gap-2 transition-all ${detected ? "border-status-alert" : "border-border"}`}>
                    {/* Avatar + Name */}
                    <div className="flex items-center gap-2">
                      <div className="w-10 h-10 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center shrink-0">
                        <span className="text-[14px] font-mono text-primary font-bold">
                          {s.name.slice(0, 2).toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <div className="text-[10px] font-mono text-foreground uppercase leading-tight truncate max-w-[90px]">{s.name}</div>
                        <div className="text-[8px] font-mono text-muted-foreground">
                          {s.enrolled_at ? new Date(s.enrolled_at).toLocaleDateString() : "UNKNOWN"}
                        </div>
                      </div>
                    </div>
                    {/* Status */}
                    {detected ? (
                      <div className="flex items-center gap-1 text-[8px] font-mono text-status-alert">
                        <AlertTriangle size={10} />
                        <span className="animate-pulse">DETECTED ON {activeCamera}</span>
                      </div>
                    ) : (
                      <div className="text-[8px] font-mono text-status-online">STATUS: ACTIVE</div>
                    )}
                    {/* Remove */}
                    <button onClick={() => handleRemove(s.name)}
                      className="text-[8px] font-mono uppercase text-status-alert/70 hover:text-status-alert border border-status-alert/30 hover:border-status-alert/60 px-2 py-0.5 transition-all self-start">
                      REMOVE
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* TRACKED PERSONS WATCHLIST (cross-camera flagged) */}
      {trackedPersons.length > 0 && (
        <div className="border-t border-border shrink-0 px-3 py-2 max-h-56 overflow-y-auto">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] font-mono text-yellow-400 uppercase tracking-widest flex items-center gap-1">
              <Shield size={10} /> FLAGGED TRACKED PERSONS ({trackedPersons.length})
            </span>
            <button onClick={loadTrackedPersons} disabled={trackedLoading} className="text-muted-foreground hover:text-foreground">
              <RefreshCw size={10} className={trackedLoading ? "animate-spin" : ""} />
            </button>
          </div>
          <div className="space-y-1.5">
            {trackedPersons.map(p => (
              <div key={p.global_id} className="border border-yellow-500/30 bg-yellow-500/5 p-2 flex items-center gap-3">
                <img
                  src={`/api/persons/${p.global_id}/snapshot.jpg`}
                  alt=""
                  className="w-10 h-10 object-cover border border-yellow-500/40 shrink-0"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono text-yellow-400 truncate">
                    {p.display_name || p.watchlist_meta?.display_name || p.global_id}
                  </div>
                  <div className="text-[9px] font-mono text-muted-foreground flex items-center gap-1 mt-0.5">
                    <Camera size={8} /> {p.last_seen_camera || "—"} · {p.last_seen_ts?.slice(0, 19) || "—"}
                  </div>
                </div>
                <button
                  onClick={() => removeFromTrackedWatchlist(p.global_id)}
                  className="text-[8px] font-mono text-status-alert/70 hover:text-status-alert border border-status-alert/30 px-2 py-0.5 shrink-0">
                  REMOVE
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* RIGHT: Live FRS Feed (40%) */}
      <div className="flex-[2] flex flex-col overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-panel shrink-0">
          <div className={`w-1.5 h-1.5 rounded-full ${activeCamera ? "bg-status-online animate-pulse" : "bg-muted-foreground"}`} />
          <span className="text-[10px] font-mono text-foreground uppercase tracking-wider">LIVE FRS DETECTIONS</span>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {(state.recent_faces || []).map((face, i) => (
            <div key={i} className={`flex items-center gap-2 border p-2 ${face.watchlist_hit ? "border-status-alert/50 bg-status-alert/5" : "border-border"}`}>
              <div className={`w-12 h-12 shrink-0 flex items-center justify-center border ${face.watchlist_hit ? "border-status-alert bg-status-alert/10" : "border-border/40 bg-border/20"}`}>
                {face.watchlist_hit ? <AlertTriangle size={16} className="text-status-alert" /> : <Users size={14} className="text-muted-foreground/40" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className={`text-[10px] font-mono uppercase ${face.watchlist_hit ? "text-status-alert" : "text-muted-foreground"}`}>
                  {face.identity || "ANONYMOUS"}
                </div>
                <div className="text-[9px] font-mono text-muted-foreground">
                  {face.gender || "?"} {face.age ? `// AGE: ${face.age}` : ""}
                </div>
                <div className="h-1 bg-border mt-1">
                  <div className="h-full bg-primary/60" style={{ width: `${Math.min(100, (face.confidence || 0.5) * 100)}%` }} />
                </div>
              </div>
            </div>
          ))}
          {(!state.recent_faces || state.recent_faces.length === 0) && (
            <div className="text-center text-[9px] font-mono text-muted-foreground/50 uppercase mt-8">
              NO FACE DETECTIONS
            </div>
          )}
        </div>

        {/* Gender Analytics */}
        <div className="border-t border-border p-3 shrink-0">
          <div className="text-[8px] font-mono text-muted-foreground uppercase mb-2">GENDER ANALYTICS // SESSION</div>
          <CrowdDensityGauge
            peopleCount={state.people_count}
            crowdDensity={state.crowd_density}
            peopleTotalCount={(state as any).people_total_count || 0}
            zoneCount={state.zone_count || 0}
            genderStats={state.gender_stats}
          />
        </div>
      </div>

      {/* Enroll Modal */}
      {enrollOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80">
          <div className="w-[440px] bg-panel border border-border">
            <div className="px-4 pt-4 pb-2 border-b border-border flex items-center justify-between">
              <span className="text-[11px] font-mono tracking-widest text-primary uppercase">ENROLL SUBJECT TO WATCHLIST</span>
              <button onClick={() => setEnrollOpen(false)} className="text-muted-foreground hover:text-foreground text-sm">✕</button>
            </div>
            <div className="p-4 space-y-3">
              <div>
                <label className="text-[8px] font-mono text-muted-foreground uppercase block mb-1">SUBJECT PHOTO</label>
                <input type="file" accept="image/*" onChange={e => setEnrollFile(e.target.files?.[0] || null)}
                  className="w-full text-[11px] font-mono" />
                {enrollFile && <div className="text-[8px] font-mono text-muted-foreground mt-1">{enrollFile.name}</div>}
              </div>
              <div>
                <label className="text-[8px] font-mono text-muted-foreground uppercase block mb-1">SUBJECT NAME / ID</label>
                <input value={enrollName} onChange={e => setEnrollName(e.target.value)}
                  placeholder="JOHN_DOE_001 (no spaces)"
                  className="w-full text-[11px] font-mono bg-background border border-border px-3 py-1.5 text-foreground placeholder:text-muted-foreground/50" />
                {enrollName && !/^[A-Za-z0-9_-]+$/.test(enrollName) && (
                  <div className="text-[8px] font-mono text-status-alert mt-0.5">Only letters, numbers, hyphens, underscores</div>
                )}
              </div>
              <div className="flex gap-2">
                <button onClick={() => setEnrollOpen(false)}
                  className="flex-1 py-2 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground transition-all">CANCEL</button>
                <button onClick={handleEnroll} disabled={!enrollFile || !enrollName || enrolling}
                  className="flex-1 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase hover:bg-primary/25 disabled:opacity-40 transition-all">
                  {enrolling ? "ENROLLING..." : "ENROLL SUBJECT"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
