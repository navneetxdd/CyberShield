import { useEffect, useRef, useState } from "react";
import { Network, Camera, User, AlertTriangle, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { getConfig } from "@/lib/config";

// ── types ─────────────────────────────────────────────────────────────────────

interface GraphNode {
  id: string;
  type: "person" | "camera";
  label: string;
  threat_level?: string;
  snapshot_url?: string | null;
  meta?: Record<string, string>;
  // layout
  x?: number;
  y?: number;
}

interface GraphEdge {
  id: string;
  from: string;
  to: string;
  tracklet_id: string;
  timestamp?: string;
  end_ts?: string;
  frame_count?: number;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ── SVG entity graph ──────────────────────────────────────────────────────────

const W = 720;
const H = 420;

function layoutNodes(nodes: GraphNode[]): GraphNode[] {
  const persons = nodes.filter(n => n.type === "person");
  const cameras = nodes.filter(n => n.type === "camera");

  // Persons arranged horizontally in the middle row
  const personY = H / 2;
  persons.forEach((p, i) => {
    p.x = (W / (persons.length + 1)) * (i + 1);
    p.y = personY;
  });

  // Cameras arranged in an arc above and below
  cameras.forEach((c, i) => {
    const angle = (Math.PI / (cameras.length + 1)) * (i + 1);
    const radius = 160;
    const personX = persons[0]?.x ?? W / 2;
    c.x = personX + radius * Math.cos(Math.PI - angle);
    c.y = personY - 80 - radius * Math.abs(Math.sin(angle)) * 0.7;
  });

  return nodes;
}

function arrowPath(x1: number, y1: number, x2: number, y2: number, rSrc: number, rDst: number) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const sx = x1 + ux * rSrc;
  const sy = y1 + uy * rSrc;
  const ex = x2 - ux * rDst;
  const ey = y2 - uy * rDst;
  return { sx, sy, ex, ey, mx: (sx + ex) / 2, my: (sy + ey) / 2 };
}

function fmt(ts?: string) {
  if (!ts) return "";
  try { return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
  catch { return ts.slice(11, 19) || ts; }
}

function EntityGraph({ data, onSelectNode }: { data: GraphData; onSelectNode: (n: GraphNode) => void }) {
  const laid = layoutNodes(data.nodes.map(n => ({ ...n })));
  const byId = Object.fromEntries(laid.map(n => [n.id, n]));

  const PERSON_RX = 52;
  const PERSON_RY = 28;
  const CAM_R = 30;

  const threatColor: Record<string, string> = {
    HIGH: "#ef4444",
    MEDIUM: "#f59e0b",
    LOW: "#22c55e",
    UNKNOWN: "#6b7280",
  };

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${W} ${H}`}
      className="border border-border bg-panel"
      style={{ fontFamily: "monospace" }}
    >
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="hsl(var(--primary))" opacity="0.7" />
        </marker>
        <marker id="arrowhead-dim" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="hsl(var(--muted-foreground))" opacity="0.4" />
        </marker>
      </defs>

      {/* Edges */}
      {data.edges.map(edge => {
        const src = byId[edge.from];
        const dst = byId[edge.to];
        if (!src?.x || !dst?.x) return null;
        const srcR = src.type === "person" ? PERSON_RX : CAM_R;
        const dstR = dst.type === "person" ? PERSON_RX : CAM_R;
        const { sx, sy, ex, ey, mx, my } = arrowPath(src.x, src.y!, dst.x, dst.y!, srcR, dstR);
        return (
          <g key={edge.id}>
            <line
              x1={sx} y1={sy} x2={ex} y2={ey}
              stroke="hsl(var(--primary))" strokeWidth="1.5" strokeOpacity="0.55"
              strokeDasharray="6 3"
              markerEnd="url(#arrowhead)"
            />
            {edge.timestamp && (
              <text x={mx} y={my - 6} textAnchor="middle" fontSize="8" fill="hsl(var(--muted-foreground))" opacity="0.8">
                {fmt(edge.timestamp)}
              </text>
            )}
            {edge.frame_count && (
              <text x={mx} y={my + 10} textAnchor="middle" fontSize="7" fill="hsl(var(--muted-foreground))" opacity="0.5">
                {edge.frame_count}f
              </text>
            )}
          </g>
        );
      })}

      {/* Camera nodes */}
      {laid.filter(n => n.type === "camera").map(node => (
        <g key={node.id} style={{ cursor: "pointer" }} onClick={() => onSelectNode(node)}>
          <circle cx={node.x} cy={node.y} r={CAM_R} fill="hsl(var(--panel))" stroke="hsl(var(--border))" strokeWidth="1.5" />
          <text x={node.x} y={(node.y ?? 0) - 8} textAnchor="middle" fontSize="9" fill="hsl(var(--muted-foreground))">
            ◼ CAM
          </text>
          <text x={node.x} y={(node.y ?? 0) + 7} textAnchor="middle" fontSize="8" fill="hsl(var(--foreground))" fontWeight="bold">
            {node.label.replace("camera_", "")}
          </text>
          <text x={node.x} y={(node.y ?? 0) + 52} textAnchor="middle" fontSize="8" fill="hsl(var(--muted-foreground))">
            {node.label}
          </text>
        </g>
      ))}

      {/* Person nodes */}
      {laid.filter(n => n.type === "person").map(node => {
        const color = threatColor[node.threat_level ?? "UNKNOWN"];
        return (
          <g key={node.id} style={{ cursor: "pointer" }} onClick={() => onSelectNode(node)}>
            <ellipse cx={node.x} cy={node.y} rx={PERSON_RX + 4} ry={PERSON_RY + 4}
              fill="none" stroke={color} strokeWidth="1" strokeOpacity="0.3" strokeDasharray="4 2" />
            <ellipse cx={node.x} cy={node.y} rx={PERSON_RX} ry={PERSON_RY}
              fill="hsl(var(--panel))" stroke={color} strokeWidth="2" />
            <text x={node.x} y={(node.y ?? 0) - 6} textAnchor="middle" fontSize="9" fill={color} fontWeight="bold" letterSpacing="1">
              ◉ SUBJECT
            </text>
            <text x={node.x} y={(node.y ?? 0) + 10} textAnchor="middle" fontSize="10" fill="hsl(var(--foreground))" fontWeight="bold">
              {node.label}
            </text>
            {node.threat_level && (
              <text x={node.x} y={(node.y ?? 0) + 48} textAnchor="middle" fontSize="8" fill={color}>
                ▲ {node.threat_level}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ── profile panel ─────────────────────────────────────────────────────────────

const META_LABELS: Record<string, string> = {
  full_name:          "Full Name",
  dob:                "Date of Birth",
  nationality:        "Nationality",
  phone:              "Phone",
  email:              "Email",
  last_known_address: "Last Known Address",
  vehicle_reg:        "Vehicle Reg",
  vehicle_desc:       "Vehicle",
  threat_level:       "Threat Level",
  notes:              "Analyst Notes",
};

function ProfilePanel({ node, edges, onClose }: { node: GraphNode | null; edges: GraphEdge[]; onClose: () => void }) {
  if (!node) {
    return (
      <div className="border border-border bg-panel p-4 h-full flex flex-col items-center justify-center gap-2">
        <Network size={28} className="text-muted-foreground/30" />
        <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest text-center">
          Click a node to view entity details
        </div>
      </div>
    );
  }

  const nodeEdges = edges.filter(e => e.from === node.id || e.to === node.id);
  const config = getConfig();

  return (
    <div className="border border-border bg-panel h-full overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2">
          {node.type === "person"
            ? <User size={13} className="text-primary" />
            : <Camera size={13} className="text-muted-foreground" />}
          <span className="text-[10px] font-mono text-foreground uppercase tracking-wider font-bold">
            {node.type === "person" ? "SUBJECT PROFILE" : "CAMERA NODE"}
          </span>
        </div>
        <button onClick={onClose} className="text-[9px] font-mono text-muted-foreground hover:text-foreground">✕</button>
      </div>

      {/* Snapshot */}
      {node.type === "person" && node.snapshot_url && (
        <div className="p-3 border-b border-border">
          <img
            src={`${config.API_URL}${node.snapshot_url}`}
            alt="Subject snapshot"
            className="w-full max-h-40 object-cover border border-border/50 grayscale"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        </div>
      )}

      {/* Global ID */}
      <div className="px-3 py-2 border-b border-border">
        <div className="text-[8px] font-mono text-muted-foreground uppercase mb-0.5">Global ID</div>
        <div className="text-[9px] font-mono text-primary">{node.id}</div>
      </div>

      {/* Threat level badge */}
      {node.threat_level && node.threat_level !== "UNKNOWN" && (
        <div className="px-3 py-2 border-b border-border flex items-center gap-2">
          <AlertTriangle size={11} className={
            node.threat_level === "HIGH" ? "text-red-500" :
            node.threat_level === "MEDIUM" ? "text-yellow-500" : "text-green-500"
          } />
          <span className={`text-[10px] font-mono font-bold ${
            node.threat_level === "HIGH" ? "text-red-500" :
            node.threat_level === "MEDIUM" ? "text-yellow-500" : "text-green-500"
          }`}>{node.threat_level} THREAT</span>
        </div>
      )}

      {/* Meta fields */}
      {node.meta && (
        <div className="divide-y divide-border/30">
          {Object.entries(META_LABELS).map(([key, label]) => {
            const val = node.meta?.[key];
            if (!val) return null;
            return (
              <div key={key} className="px-3 py-2">
                <div className="text-[8px] font-mono text-muted-foreground uppercase mb-0.5">{label}</div>
                <div className="text-[9px] font-mono text-foreground leading-relaxed">{val}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Camera label for camera nodes */}
      {node.type === "camera" && (
        <div className="px-3 py-2 border-b border-border">
          <div className="text-[8px] font-mono text-muted-foreground uppercase mb-0.5">Camera ID</div>
          <div className="text-[10px] font-mono text-foreground">{node.label}</div>
        </div>
      )}

      {/* Sightings / edges */}
      {nodeEdges.length > 0 && (
        <div className="px-3 pt-3">
          <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest mb-2">
            {node.type === "person" ? "Camera Sightings" : "Detections Here"}
          </div>
          <div className="space-y-1.5">
            {nodeEdges.map(e => (
              <div key={e.id} className="border border-border/40 px-2 py-1.5 text-[8px] font-mono">
                <div className="text-muted-foreground uppercase">{e.tracklet_id}</div>
                <div className="text-foreground mt-0.5">{fmt(e.timestamp)} — {fmt(e.end_ts)}</div>
                {e.frame_count && (
                  <div className="text-muted-foreground/60">{e.frame_count} frames analysed</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── main view ─────────────────────────────────────────────────────────────────

export function OSINTView() {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [tracklets, setTracklets] = useState<any[]>([]);
  const [queue, setQueue] = useState<any>(null);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      apiFetch("/api/osint/graph") as Promise<GraphData>,
      apiFetch("/api/records/tracklets?limit=50") as Promise<any>,
      apiFetch("/api/metrics/worker_queue") as Promise<any>,
    ])
      .then(([graphData, trackletData, queueData]) => {
        setGraph(graphData);
        setTracklets(Array.isArray(trackletData?.records) ? trackletData.records : []);
        setQueue(queueData || null);
      })
      .catch(err => setError(String(err?.message || "Failed to load OSINT data")))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadData(); }, []);

  useEffect(() => {
    const config = getConfig();
    const ws = new WebSocket(`${config.WS_URL}/ws/state?api_key=${encodeURIComponent(config.API_KEY || "")}`);
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        setIncidents(prev => [payload, ...prev].slice(0, 20));
      } catch { /* ignore */ }
    };
    return () => ws.close();
  }, []);

  const watchlistNodes = graph?.nodes.filter(n => n.type === "person") ?? [];
  const cameraNodes = graph?.nodes.filter(n => n.type === "camera") ?? [];

  return (
    <div className="h-full overflow-auto p-4 space-y-4">
      {/* Header */}
      <div className="border border-border bg-panel px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Network size={18} className="text-primary" />
          <div className="text-[11px] font-mono text-primary uppercase tracking-widest">OSINT / Entity Continuity Graph</div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-[9px] font-mono text-muted-foreground uppercase">
            {queue ? `QUEUE: ${queue.pending_enrichments ?? 0} PENDING` : "QUEUE OFFLINE"}
          </div>
          <button
            onClick={loadData}
            className="flex items-center gap-1 px-2 py-1 border border-border text-[9px] font-mono text-muted-foreground hover:text-foreground transition-all"
          >
            <RefreshCw size={10} />
            REFRESH
          </button>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          ["Watchlisted", watchlistNodes.length],
          ["Cameras", cameraNodes.length],
          ["Tracklets", tracklets.length],
          ["Incidents", incidents.length],
        ].map(([label, value]) => (
          <div key={label as string} className="border border-border bg-panel p-3">
            <div className="text-[9px] font-mono text-muted-foreground uppercase">{label}</div>
            <div className="text-[22px] font-mono text-foreground font-bold mt-1">{value as number}</div>
          </div>
        ))}
      </div>

      {/* Graph + Profile */}
      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 280px" }}>
        <div className="space-y-2">
          <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest px-1">
            Cross-Camera Movement Graph
          </div>

          {loading && (
            <div className="border border-border bg-panel h-64 flex items-center justify-center">
              <div className="text-[10px] font-mono text-muted-foreground uppercase animate-pulse">Loading graph...</div>
            </div>
          )}

          {error && (
            <div className="border border-status-alert/40 bg-panel p-4 text-[9px] font-mono text-status-alert">
              {error}
            </div>
          )}

          {!loading && !error && graph && graph.nodes.length === 0 && (
            <div className="border border-border bg-panel h-64 flex items-center justify-center">
              <div className="text-center">
                <Network size={28} className="text-muted-foreground/30 mx-auto mb-2" />
                <div className="text-[9px] font-mono text-muted-foreground uppercase">No watchlisted entities detected yet</div>
                <div className="text-[8px] font-mono text-muted-foreground/60 mt-1">Enrol a person via Watchlist to appear here</div>
              </div>
            </div>
          )}

          {!loading && !error && graph && graph.nodes.length > 0 && (
            <EntityGraph
              data={graph}
              onSelectNode={setSelectedNode}
            />
          )}

          {/* Recent tracklets table */}
          {tracklets.length > 0 && (
            <div className="border border-border bg-panel">
              <div className="px-4 py-2 border-b border-border text-[10px] font-mono text-foreground uppercase tracking-wider">
                Recent Tracklets
              </div>
              <div className="max-h-48 overflow-auto">
                <table className="w-full text-[10px] font-mono">
                  <thead>
                    <tr className="border-b border-border/50 text-muted-foreground">
                      <th className="text-left px-3 py-1.5 font-normal">TRACKLET</th>
                      <th className="text-left px-3 py-1.5 font-normal">CAMERA</th>
                      <th className="text-left px-3 py-1.5 font-normal">FRAMES</th>
                      <th className="text-left px-3 py-1.5 font-normal">GLOBAL ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tracklets.slice(0, 20).map(trk => (
                      <tr key={trk.tracklet_id} className="border-b border-border/20 hover:bg-white/[0.02]">
                        <td className="px-3 py-1.5 text-muted-foreground">{trk.tracklet_id}</td>
                        <td className="px-3 py-1.5 text-foreground">{trk.camera_id}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{trk.frame_count}</td>
                        <td className="px-3 py-1.5 text-primary">{trk.resolved_global_id || "--"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Profile / details panel */}
        <div className="space-y-3">
          <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest px-1">Entity Details</div>
          <ProfilePanel
            node={selectedNode}
            edges={graph?.edges ?? []}
            onClose={() => setSelectedNode(null)}
          />

          {/* Incidents */}
          <div className="border border-border bg-panel">
            <div className="px-3 py-2 border-b border-border text-[9px] font-mono text-foreground uppercase tracking-wider">
              Live Incidents
            </div>
            <div className="max-h-40 overflow-auto p-2 space-y-1.5">
              {incidents.length === 0 ? (
                <div className="text-[9px] font-mono text-muted-foreground uppercase p-1">No incidents yet</div>
              ) : (
                incidents.map((inc, i) => (
                  <div key={`${inc.incident_id ?? i}`} className="border border-border/30 px-2 py-1.5">
                    <div className="text-[8px] font-mono text-status-warning uppercase">{inc.reason || "Continuity match"}</div>
                    <div className="text-[9px] font-mono text-foreground">{inc.tracklet_id || inc.incident_id}</div>
                    <div className="text-[8px] font-mono text-muted-foreground">Score: {inc.score ?? "--"}</div>
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
