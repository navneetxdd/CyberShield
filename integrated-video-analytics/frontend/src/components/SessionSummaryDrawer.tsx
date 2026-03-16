import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from "recharts";

interface SummaryData {
  camera_id: string;
  total_vehicles: number;
  total_people: number;
  total_plates: number;
  total_faces: number;
  watchlist_hits: number;
  gender_breakdown: Record<string, number>;
  vehicle_type_breakdown: Record<string, number>;
  top_plates: Array<{ plate_text: string; count: number }>;
  event_count_by_type: Record<string, number>;
}

const CHART_COLORS = ["#38bdf8", "#818cf8", "#6b7280", "#fbbf24", "#f87171"];
const TOOLTIP_STYLE = {
  backgroundColor: "#0a0a0f",
  border: "1px solid rgba(56,189,248,0.2)",
  fontFamily: "monospace",
  fontSize: 10,
};

interface SessionSummaryDrawerProps {
  open: boolean;
  onClose: () => void;
  cameraId: string;
}

export function SessionSummaryDrawer({ open, onClose, cameraId }: SessionSummaryDrawerProps) {
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    apiFetch<any>(`/api/analytics/summary?camera_id=${encodeURIComponent(cameraId)}`)
      .then(d => setSummary(d?.summary || null))
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [open, cameraId]);

  if (!open) return null;

  const genderData = summary
    ? Object.entries(summary.gender_breakdown).map(([k, v]) => ({ name: k, value: v }))
    : [];
  const vehicleData = summary
    ? Object.entries(summary.vehicle_type_breakdown).map(([k, v]) => ({ name: k, value: v }))
    : [];
  const eventData = summary
    ? Object.entries(summary.event_count_by_type).map(([k, v]) => ({ name: k, value: v }))
    : [];

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-end justify-center">
      <div className="w-full max-w-4xl border border-border bg-panel shadow-2xl max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border sticky top-0 bg-panel z-10">
          <div className="flex items-center gap-3">
            <div className="w-1.5 h-1.5 bg-primary animate-pulse" />
            <span className="text-[13px] font-mono font-bold tracking-[0.15em] uppercase text-foreground">SESSION INTELLIGENCE SUMMARY</span>
          </div>
          <div className="flex gap-2">
            <a
              href={`/api/reports/download?camera_id=${cameraId}`}
              className="text-[10px] font-mono uppercase px-3 py-1 border border-primary text-primary hover:bg-primary/10 transition-all"
            >
              DOWNLOAD REPORT
            </a>
            <button
              onClick={onClose}
              className="text-[10px] font-mono uppercase px-3 py-1 border border-border text-muted-foreground hover:text-foreground transition-all"
            >
              ✕ CLOSE
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-center text-[12px] font-mono text-primary/50 py-16">LOADING SESSION DATA...</div>
        ) : summary ? (
          <div className="p-4 space-y-4">
            {/* Row 1 — Stat cards */}
            <div className="grid grid-cols-4 gap-3">
              {[
                { label: "Total Vehicles", value: summary.total_vehicles, color: "text-primary" },
                { label: "Total People", value: summary.total_people, color: "text-secondary" },
                { label: "Plates Captured", value: summary.total_plates, color: "text-primary" },
                { label: "Faces Analyzed", value: summary.total_faces, color: "text-secondary" },
              ].map(stat => (
                <div key={stat.label} className="border border-border p-3 text-center">
                  <div className={`text-[28px] font-mono font-bold ${stat.color}`}>{stat.value}</div>
                  <div className="text-[9px] font-mono text-muted-foreground uppercase mt-1">{stat.label}</div>
                </div>
              ))}
            </div>

            {/* Row 2 — Watchlist Hits */}
            <div className="border border-border p-3 flex items-center justify-between">
              <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-widest">Watchlist Hits</span>
              <span className={`text-[32px] font-mono font-bold ${summary.watchlist_hits > 0 ? "text-status-alert" : "text-status-online"}`}>
                {summary.watchlist_hits}
              </span>
            </div>

            {/* Row 3+4 — Charts row */}
            <div className="grid grid-cols-3 gap-3">
              {/* Gender pie */}
              <div className="border border-border p-3">
                <div className="text-[9px] font-mono text-muted-foreground uppercase mb-2 tracking-widest">Gender Breakdown</div>
                <ResponsiveContainer width="100%" height={140}>
                  <PieChart>
                    <Pie data={genderData} cx="50%" cy="50%" innerRadius={35} outerRadius={55} dataKey="value">
                      {genderData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i]} />)}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Legend iconSize={8} wrapperStyle={{ fontSize: 9, fontFamily: "monospace" }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Vehicle types bar */}
              <div className="border border-border p-3">
                <div className="text-[9px] font-mono text-muted-foreground uppercase mb-2 tracking-widest">Vehicle Classes</div>
                <ResponsiveContainer width="100%" height={140}>
                  <BarChart data={vehicleData} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="name" tick={{ fill: "#4b5563", fontFamily: "monospace", fontSize: 9 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "#4b5563", fontFamily: "monospace", fontSize: 9 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Bar dataKey="value" fill="#38bdf8" opacity={0.8} name="Count" />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Event types pie */}
              <div className="border border-border p-3">
                <div className="text-[9px] font-mono text-muted-foreground uppercase mb-2 tracking-widest">Event Distribution</div>
                <ResponsiveContainer width="100%" height={140}>
                  <PieChart>
                    <Pie data={eventData} cx="50%" cy="50%" outerRadius={55} dataKey="value">
                      {eventData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i]} />)}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Legend iconSize={8} wrapperStyle={{ fontSize: 9, fontFamily: "monospace" }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Row 5 — Top plates */}
            <div className="border border-border p-3">
              <div className="text-[9px] font-mono text-muted-foreground uppercase mb-3 tracking-widest">Top 5 Plates by Frequency</div>
              <table className="w-full text-[10px] font-mono">
                <thead>
                  <tr className="border-b border-border/40">
                    {["RANK", "PLATE TEXT", "SEEN COUNT"].map(h => (
                      <th key={h} className="text-left py-1 px-2 text-muted-foreground font-normal uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {summary.top_plates.map((p, i) => (
                    <tr key={i} className={`border-b border-border/20 ${i % 2 === 0 ? "bg-white/[0.01]" : ""}`}>
                      <td className="py-1 px-2 text-muted-foreground">#{i + 1}</td>
                      <td className="py-1 px-2 text-foreground font-bold tracking-[0.15em]">{p.plate_text}</td>
                      <td className="py-1 px-2 text-primary">{p.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
