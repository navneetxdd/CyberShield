import { useEffect, useState } from "react";
import { Network } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { getConfig } from "@/lib/config";

export function OSINTView() {
  const [tracklets, setTracklets] = useState<any[]>([]);
  const [watchlist, setWatchlist] = useState<any[]>([]);
  const [queue, setQueue] = useState<any>(null);
  const [incidents, setIncidents] = useState<any[]>([]);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch("/api/records/tracklets?limit=50") as Promise<any>,
      apiFetch("/api/watchlist") as Promise<any>,
      apiFetch("/api/metrics/worker_queue") as Promise<any>,
    ])
      .then(([trackletData, watchlistData, queueData]) => {
        if (!active) return;
        setTracklets(Array.isArray(trackletData?.records) ? trackletData.records : []);
        setWatchlist(Array.isArray(watchlistData?.entries) ? watchlistData.entries : []);
        setQueue(queueData || null);
      })
      .catch(() => {
        if (!active) return;
        setTracklets([]);
        setWatchlist([]);
        setQueue(null);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const config = getConfig();
    const ws = new WebSocket(`${config.WS_URL}/ws/state?api_key=${encodeURIComponent(config.API_KEY || "")}`);
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        setIncidents((prev) => [payload, ...prev].slice(0, 20));
      } catch {
        // Ignore malformed websocket payloads.
      }
    };
    return () => ws.close();
  }, []);

  return (
    <div className="h-full overflow-auto p-4 space-y-4">
      <div className="border border-border bg-panel px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Network size={18} className="text-primary" />
          <div className="text-[11px] font-mono text-primary uppercase tracking-widest">OSINT / Cross-Camera Continuity</div>
        </div>
        <div className="text-[9px] font-mono text-muted-foreground uppercase">
          {queue ? `PENDING ${queue.pending_enrichments || 0}` : "QUEUE OFFLINE"}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          ["Tracklets", tracklets.length],
          ["Watchlist IDs", watchlist.length],
          ["Incident Buffer", incidents.length],
        ].map(([label, value]) => (
          <div key={label as string} className="border border-border bg-panel p-4">
            <div className="text-[9px] font-mono text-muted-foreground uppercase">{label}</div>
            <div className="text-[24px] font-mono text-foreground font-bold mt-2">{value as number}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="border border-border bg-panel">
          <div className="px-4 py-2 border-b border-border text-[10px] font-mono text-foreground uppercase tracking-wider">
            Recent Tracklets
          </div>
          <div className="max-h-[420px] overflow-auto">
            {tracklets.length === 0 ? (
              <div className="p-4 text-[10px] font-mono text-muted-foreground uppercase">No tracklets available yet</div>
            ) : (
              <table className="w-full text-[10px] font-mono">
                <thead>
                  <tr className="border-b border-border/50 text-muted-foreground">
                    <th className="text-left px-3 py-2 font-normal">TRACKLET</th>
                    <th className="text-left px-3 py-2 font-normal">CAMERA</th>
                    <th className="text-left px-3 py-2 font-normal">FRAMES</th>
                    <th className="text-left px-3 py-2 font-normal">GLOBAL ID</th>
                  </tr>
                </thead>
                <tbody>
                  {tracklets.slice(0, 50).map((tracklet) => (
                    <tr key={tracklet.tracklet_id} className="border-b border-border/20">
                      <td className="px-3 py-2 text-foreground">{tracklet.tracklet_id}</td>
                      <td className="px-3 py-2 text-muted-foreground">{tracklet.camera_id}</td>
                      <td className="px-3 py-2 text-muted-foreground">{tracklet.frame_count}</td>
                      <td className="px-3 py-2 text-primary">{tracklet.resolved_global_id || "--"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="border border-border bg-panel">
            <div className="px-4 py-2 border-b border-border text-[10px] font-mono text-foreground uppercase tracking-wider">
              Worker Queue
            </div>
            <div className="p-4 grid grid-cols-3 gap-3 text-center">
              {[
                ["Pending", queue?.pending_enrichments ?? 0],
                ["Buffers", queue?.active_tracklet_buffers ?? 0],
                ["Incidents", queue?.incident_buffer ?? 0],
              ].map(([label, value]) => (
                <div key={label as string} className="border border-border/40 p-3">
                  <div className="text-[9px] font-mono text-muted-foreground uppercase">{label}</div>
                  <div className="text-[18px] font-mono text-foreground font-bold mt-1">{value as number}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-border bg-panel">
            <div className="px-4 py-2 border-b border-border text-[10px] font-mono text-foreground uppercase tracking-wider">
              Recent Incidents
            </div>
            <div className="max-h-[220px] overflow-auto p-3 space-y-2">
              {incidents.length === 0 ? (
                <div className="text-[10px] font-mono text-muted-foreground uppercase">No incident data yet</div>
              ) : (
                incidents.map((incident, index) => (
                  <div key={`${incident.incident_id || index}`} className="border border-border/40 p-3">
                    <div className="text-[9px] font-mono text-status-warning uppercase">{incident.reason || "Potential continuity match"}</div>
                    <div className="text-[10px] font-mono text-foreground mt-1">{incident.tracklet_id || incident.incident_id}</div>
                    <div className="text-[9px] font-mono text-muted-foreground mt-1">Score: {incident.score ?? "--"}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
