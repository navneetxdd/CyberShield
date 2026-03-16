import { useEffect, useState } from "react";
import { AlertTriangle, Shield, Users } from "lucide-react";
import { CyberShieldState } from "../pages/Index";
import { CrowdDensityGauge } from "../components/CrowdDensityGauge";
import { apiAssetUrl, apiFetch } from "../lib/api";

interface WatchlistViewProps {
  state: CyberShieldState;
  activeCamera: string;
}

interface WatchlistEntry {
  identity: string;
  display_name?: string;
  global_id: string;
  last_seen_ts?: string;
  snapshot_url?: string;
}

export function WatchlistView({ state, activeCamera }: WatchlistViewProps) {
  const [subjects, setSubjects] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [enrollName, setEnrollName] = useState("");
  const [enrollFile, setEnrollFile] = useState<File | null>(null);
  const [enrolling, setEnrolling] = useState(false);

  const recentlyDetected = (name: string) => {
    return state.event_logs?.some((event) => event.detail?.includes(name) && event.type?.includes("Watchlist"));
  };

  const loadSubjects = async () => {
    setLoading(true);
    try {
      const data = await apiFetch<{ entries?: WatchlistEntry[] }>("/api/watchlist");
      setSubjects(Array.isArray(data?.entries) ? data.entries : []);
    } catch {
      setSubjects([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSubjects();
  }, []);

  const handleEnroll = async () => {
    if (!enrollFile || !enrollName.trim()) return;
    if (!/^[A-Za-z0-9_-]+$/.test(enrollName)) {
      alert("Name must use letters, numbers, hyphens, or underscores only.");
      return;
    }
    setEnrolling(true);
    try {
      const form = new FormData();
      form.append("name", enrollName);
      form.append("file", enrollFile);
      await apiFetch("/api/watchlist", { method: "POST", body: form });
      setEnrollOpen(false);
      setEnrollName("");
      setEnrollFile(null);
      await loadSubjects();
    } catch {
      alert("Enrollment failed.");
    } finally {
      setEnrolling(false);
    }
  };

  const handleRemove = async (subject: WatchlistEntry) => {
    if (!confirm(`Remove ${subject.identity} from the watchlist?`)) return;
    try {
      await apiFetch(`/api/watchlist/${encodeURIComponent(subject.global_id)}`, { method: "DELETE" });
      setSubjects((prev) => prev.filter((item) => item.global_id !== subject.global_id));
    } catch {
      alert("Removal failed.");
    }
  };

  const filtered = subjects.filter((subject) => subject.identity.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="h-full flex overflow-hidden">
      <div className="flex-[3] flex flex-col border-r border-border overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-panel shrink-0">
          <span className="text-[10px] font-mono text-foreground uppercase tracking-wider">
            WATCHLIST // {subjects.length} SUBJECTS ENROLLED
          </span>
          <button
            onClick={() => setEnrollOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase hover:bg-primary/25 transition-all"
          >
            <Shield size={11} /> ENROLL SUBJECT
          </button>
        </div>

        <div className="px-3 py-2 border-b border-border shrink-0">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="SEARCH SUBJECT..."
            className="w-full text-[11px] font-mono bg-background border border-border px-3 py-1.5 text-foreground placeholder:text-muted-foreground/50"
          />
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {loading ? (
            <div className="grid grid-cols-3 gap-2">
              {[1, 2, 3].map((item) => <div key={item} className="skeleton h-24 border border-border" />)}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <Users size={40} className="text-muted-foreground/40" />
              <div className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">NO SUBJECTS ENROLLED</div>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {filtered.map((subject) => {
                const detected = recentlyDetected(subject.identity);
                return (
                  <div
                    key={subject.global_id}
                    className={`border p-3 flex flex-col gap-2 transition-all ${detected ? "border-status-alert" : "border-border"}`}
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-12 h-12 border border-primary/30 bg-primary/10 overflow-hidden flex items-center justify-center shrink-0">
                        {subject.snapshot_url ? (
                          <img src={apiAssetUrl(subject.snapshot_url)} alt={subject.identity} className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-[14px] font-mono text-primary font-bold">{subject.identity.slice(0, 2).toUpperCase()}</span>
                        )}
                      </div>
                      <div className="min-w-0">
                        <div className="text-[10px] font-mono text-foreground uppercase leading-tight truncate">{subject.identity}</div>
                        <div className="text-[8px] font-mono text-muted-foreground truncate">{subject.global_id}</div>
                      </div>
                    </div>
                    {detected ? (
                      <div className="flex items-center gap-1 text-[8px] font-mono text-status-alert">
                        <AlertTriangle size={10} />
                        <span className="animate-pulse">DETECTED ON {activeCamera || "ACTIVE FEED"}</span>
                      </div>
                    ) : (
                      <div className="text-[8px] font-mono text-status-online">STATUS: ACTIVE</div>
                    )}
                    <button
                      onClick={() => handleRemove(subject)}
                      className="text-[8px] font-mono uppercase text-status-alert/70 hover:text-status-alert border border-status-alert/30 hover:border-status-alert/60 px-2 py-0.5 transition-all self-start"
                    >
                      REMOVE
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="flex-[2] flex flex-col overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-panel shrink-0">
          <div className={`w-1.5 h-1.5 rounded-full ${activeCamera ? "bg-status-online animate-pulse" : "bg-muted-foreground"}`} />
          <span className="text-[10px] font-mono text-foreground uppercase tracking-wider">LIVE FRS DETECTIONS</span>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {(state.recent_faces || []).map((face, index) => (
            <div
              key={index}
              className={`flex items-center gap-2 border p-2 ${face.watchlist_hit ? "border-status-alert/50 bg-status-alert/5" : "border-border"}`}
            >
              <div className="w-12 h-12 shrink-0 border border-border/40 bg-border/20 overflow-hidden flex items-center justify-center">
                {face.snapshot_url ? (
                  <img src={apiAssetUrl(face.snapshot_url)} alt={face.identity || "Anonymous"} className="w-full h-full object-cover" />
                ) : face.watchlist_hit ? (
                  <AlertTriangle size={16} className="text-status-alert" />
                ) : (
                  <Users size={14} className="text-muted-foreground/40" />
                )}
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
            <div className="text-center text-[9px] font-mono text-muted-foreground/50 uppercase mt-8">NO FACE DETECTIONS</div>
          )}
        </div>

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

      {enrollOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80">
          <div className="w-[440px] bg-panel border border-border">
            <div className="px-4 pt-4 pb-2 border-b border-border flex items-center justify-between">
              <span className="text-[11px] font-mono tracking-widest text-primary uppercase">ENROLL SUBJECT TO WATCHLIST</span>
              <button onClick={() => setEnrollOpen(false)} className="text-muted-foreground hover:text-foreground text-sm">×</button>
            </div>
            <div className="p-4 space-y-3">
              <div>
                <label className="text-[8px] font-mono text-muted-foreground uppercase block mb-1">SUBJECT PHOTO</label>
                <input type="file" accept="image/*" onChange={(e) => setEnrollFile(e.target.files?.[0] || null)} className="w-full text-[11px] font-mono" />
                {enrollFile && <div className="text-[8px] font-mono text-muted-foreground mt-1">{enrollFile.name}</div>}
              </div>
              <div>
                <label className="text-[8px] font-mono text-muted-foreground uppercase block mb-1">SUBJECT NAME / ID</label>
                <input
                  value={enrollName}
                  onChange={(e) => setEnrollName(e.target.value.toUpperCase().replace(/\s/g, "_"))}
                  placeholder="SUBJECT_ALPHA_01"
                  className="w-full text-[11px] font-mono bg-background border border-border px-3 py-1.5 text-foreground placeholder:text-muted-foreground/50"
                />
                {enrollName && !/^[A-Za-z0-9_-]+$/.test(enrollName) && (
                  <div className="text-[8px] font-mono text-status-alert mt-0.5">Only letters, numbers, hyphens, underscores</div>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setEnrollOpen(false)}
                  className="flex-1 py-2 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground transition-all"
                >
                  CANCEL
                </button>
                <button
                  onClick={handleEnroll}
                  disabled={!enrollFile || !enrollName || enrolling}
                  className="flex-1 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase hover:bg-primary/25 disabled:opacity-40 transition-all"
                >
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
