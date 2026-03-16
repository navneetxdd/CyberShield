import { useState, useEffect, useRef } from "react";
import { apiFetch, apiUpload } from "@/lib/api";
import { toast } from "sonner";

interface WatchlistEntry {
  name: string;
  filename: string;
  enrolled_at: string;
}

interface WatchlistPanelProps {
  eventLogs: any[];
  onEnroll?: () => void;
}

function formatDate(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export function WatchlistPanel({ eventLogs, onEnroll }: WatchlistPanelProps) {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [enrollName, setEnrollName] = useState("");
  const [enrollFile, setEnrollFile] = useState<File | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const fetchWatchlist = async () => {
    try {
      const data = await apiFetch<any>("/api/watchlist/files");
      const normalized = (data?.entries || []).map((item: any) => ({
        name: item.identity,
        filename: item.filename,
        enrolled_at: item.updated_at ? new Date(item.updated_at * 1000).toISOString() : new Date().toISOString(),
      }));
      setEntries(normalized);
    } catch {
      toast.error("Could not load watchlist");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWatchlist();
    const interval = setInterval(fetchWatchlist, 15000);
    return () => clearInterval(interval);
  }, []);

  // Detect which entries have a recent alert hit
  const recentHitNames = new Set<string>();
  const now = Date.now();
  (eventLogs || []).forEach((log: any) => {
    if ((log.type || "").includes("TACTICAL") || (log.type || "").includes("WATCHLIST")) {
      const detail = (log.detail || "").toUpperCase();
      entries.forEach((e) => {
        if (detail.includes(e.name.toUpperCase().replace(/_/g, " "))) {
          recentHitNames.add(e.name);
        }
      });
    }
  });

  const handleEnroll = async () => {
    if (!enrollName.trim() || !enrollFile) {
      toast.error("Name and photo are required.");
      return;
    }
    const safeName = enrollName.trim().replace(/[^a-zA-Z0-9_]/g, "_").slice(0, 32);
    setEnrolling(true);
    try {
      const formData = new FormData();
      formData.append("name", safeName);
      formData.append("file", enrollFile);
      const data = await apiUpload(`/api/watchlist/files`, formData);
      if ((data as any)?.status === "success") {
        toast.success(`Subject ${safeName.toUpperCase()} enrolled.`);
        setEnrollOpen(false);
        setEnrollName("");
        setEnrollFile(null);
        fetchWatchlist();
        if (onEnroll) onEnroll();
      }
    } catch (err: any) {
      toast.error(`Enrollment failed: ${err?.message || "Unknown error"}`);
    } finally {
      setEnrolling(false);
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await apiFetch(`/api/watchlist/files/${name}`, { method: "DELETE" });
      setEntries(prev => prev.filter(e => e.name !== name));
      setConfirmDelete(null);
      toast.success(`${name.toUpperCase()} removed from watchlist.`);
    } catch (err: any) {
      toast.error(`Remove failed: ${err?.message}`);
    }
  };

  return (
    <div className="border border-border bg-panel flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="p-2 border-b border-border flex justify-between items-center shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-status-alert animate-pulse" />
          <span className="text-[11px] font-mono font-bold tracking-[0.1em] uppercase text-foreground">WATCHLIST</span>
          <span className="text-[9px] font-mono text-muted-foreground">({entries.length})</span>
        </div>
        <button
          onClick={() => setEnrollOpen(true)}
          className="text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 border border-primary/40 text-primary hover:bg-primary/10 transition-all"
        >
          + ENROLL
        </button>
      </div>

      {/* Enroll Modal */}
      {enrollOpen && (
        <div className="absolute inset-0 z-50 bg-background/90 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-72 border border-border bg-panel p-4 space-y-3">
            <div className="text-[11px] font-mono font-bold text-primary uppercase tracking-widest">Enroll Subject</div>
            <div>
              <label className="text-[9px] font-mono text-muted-foreground uppercase block mb-1">Subject Name</label>
              <input
                className="w-full bg-background border border-border text-foreground text-[11px] font-mono px-2 py-1 outline-none focus:border-primary"
                placeholder="e.g. VANCE_MARCUS"
                value={enrollName}
                maxLength={32}
                onChange={e => setEnrollName(e.target.value)}
              />
            </div>
            <div>
              <label className="text-[9px] font-mono text-muted-foreground uppercase block mb-1">Photo (clear, front-facing)</label>
              <input
                type="file"
                accept="image/*"
                className="text-[10px] font-mono text-muted-foreground w-full"
                onChange={e => setEnrollFile(e.target.files?.[0] || null)}
              />
            </div>
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleEnroll}
                disabled={enrolling}
                className="flex-1 py-1 text-[10px] font-mono uppercase bg-primary/10 border border-primary text-primary hover:bg-primary/20 disabled:opacity-50"
              >
                {enrolling ? "ENROLLING..." : "SUBMIT"}
              </button>
              <button
                onClick={() => { setEnrollOpen(false); setEnrollName(""); setEnrollFile(null); }}
                className="flex-1 py-1 text-[10px] font-mono uppercase border border-border text-muted-foreground hover:text-foreground"
              >
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {confirmDelete && (
        <div className="absolute inset-0 z-50 bg-background/90 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-64 border border-status-alert bg-panel p-4 space-y-3">
            <div className="text-[11px] font-mono font-bold text-status-alert uppercase">Confirm Remove</div>
            <div className="text-[10px] font-mono text-foreground">Remove <span className="text-status-alert font-bold">{confirmDelete.toUpperCase()}</span> from watchlist?</div>
            <div className="flex gap-2">
              <button onClick={() => handleDelete(confirmDelete)} className="flex-1 py-1 text-[10px] font-mono uppercase bg-status-alert/10 border border-status-alert text-status-alert hover:bg-status-alert/20">REMOVE</button>
              <button onClick={() => setConfirmDelete(null)} className="flex-1 py-1 text-[10px] font-mono uppercase border border-border text-muted-foreground hover:text-foreground">CANCEL</button>
            </div>
          </div>
        </div>
      )}

      {/* Entry List */}
      <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5 min-h-0">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="border border-border/30 p-2 animate-pulse">
              <div className="h-3 bg-muted/20 w-2/3 mb-1.5" />
              <div className="h-2 bg-muted/10 w-1/2" />
            </div>
          ))
        ) : entries.length === 0 ? (
          <div className="text-[10px] font-mono text-muted-foreground/50 text-center p-6">
            NO SUBJECTS ENROLLED<br />
            <span className="text-[9px] opacity-50">USE ENROLL TO ADD WATCHLIST TARGETS</span>
          </div>
        ) : (
          entries.map((entry) => {
            const isHit = recentHitNames.has(entry.name);
            return (
              <div key={entry.name} className={`border p-2 transition-all duration-300 ${isHit ? "border-status-alert bg-status-alert/5 animate-threat-pulse" : "border-border/40 bg-surface"}`}>
                {isHit && (
                  <div className="text-[9px] font-mono text-status-alert font-bold animate-pulse mb-1">⚠ ACTIVE DETECTION</div>
                )}
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <div className={`text-[11px] font-mono font-bold uppercase truncate ${isHit ? "text-status-alert" : "text-foreground"}`}>
                      {entry.name.replace(/_/g, " ")}
                    </div>
                    <div className="text-[9px] font-mono text-muted-foreground mt-0.5">{formatDate(entry.enrolled_at)}</div>
                    <div className="mt-1 flex gap-1 items-center">
                      <div className="w-1 h-1 rounded-full bg-status-online" />
                      <span className="text-[8px] font-mono text-status-online uppercase">ACTIVE</span>
                    </div>
                  </div>
                  <button
                    onClick={() => setConfirmDelete(entry.name)}
                    className="text-[9px] font-mono text-muted-foreground hover:text-status-alert px-1 py-0.5 border border-transparent hover:border-status-alert/40 transition-all shrink-0"
                  >
                    ✕
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
