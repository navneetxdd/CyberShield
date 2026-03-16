import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "@/lib/api";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend
} from "recharts";

const RANGES = ["1H", "6H", "24H", "ALL"] as const;
type Range = typeof RANGES[number];


const TOOLTIP_STYLE = {
  backgroundColor: "#0a0a0f",
  border: "1px solid rgba(56,189,248,0.2)",
  borderRadius: 0,
  fontFamily: "monospace",
  fontSize: 10,
};

const DARK_LABEL_STYLE = { fill: "#4b5563", fontFamily: "monospace", fontSize: 10 };

export default function Analytics() {
  const [range, setRange] = useState<Range>("6H");
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [plates, setPlates] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;
    setLoading(true);
    setError(null);

    const limitByRange: Record<Range, number> = {
      "1H": 60,
      "6H": 360,
      "24H": 1440,
      "ALL": 5000,
    };
    const limit = limitByRange[range];

    const fetchMetrics = apiFetch<any>(`/api/metrics?limit=${limit}`)
      .then(d => {
        if (!isActive) return;
        const metrics = Array.isArray(d?.history) ? d.history : [];
        setHistory(metrics.map((item: any) => ({
          bucket: item.timestamp ? new Date(item.timestamp).toLocaleTimeString("en-GB", { hour12: false }) : "",
          avg_vehicles: Number(item.vehicle_count || 0),
          avg_people: Number(item.people_count || 0),
          avg_zone: Number(item.zone_count || 0),
          max_vehicles: Number(item.vehicle_count || 0),
          max_people: Number(item.people_count || 0),
        })));
      });

    const fetchPlates = apiFetch<any>(`/api/records/plates?limit=100`)
      .then(d => {
        if (!isActive) return;
        setPlates(Array.isArray(d?.records) ? d.records : []);
      });

    Promise.all([fetchMetrics, fetchPlates])
      .catch((err) => {
        if (!isActive) return;
        console.error("Analytics fetch error", err);
        setError("Failed to load analytics from backend.");
      })
      .finally(() => {
        if (isActive) setLoading(false);
      });

    return () => { isActive = false; };
  }, [range]);

  const filteredPlates = useMemo(() =>
    plates.filter(p =>
      String(p.plate_text || "").toLowerCase().includes(search.toLowerCase()) ||
      String(p.vehicle_type || "").toLowerCase().includes(search.toLowerCase())
    ), [plates, search]);

  return (
    <div className="min-h-screen bg-background text-foreground font-mono p-4 space-y-4">
      {/* Header */}
      <header className="flex items-center justify-between border border-border bg-panel px-4 py-2">
        <div className="flex items-center gap-4">
          <div className="w-2 h-2 bg-primary glow-cyan" />
          <span className="text-[12px] font-bold tracking-[0.2em] text-primary uppercase">CYBERSHIELD // ANALYTICS COMMAND</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {RANGES.map(r => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-3 py-1 text-[10px] font-mono uppercase tracking-widest border transition-all ${range === r ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/30"}`}
              >
                {r}
              </button>
            ))}
          </div>
          <Link
            to="/"
            className="px-3 py-1 text-[10px] font-mono uppercase tracking-widest border border-border text-muted-foreground hover:border-primary/50 hover:text-foreground transition-all"
          >
            ← LIVE VIEW
          </Link>
        </div>
      </header>

      {loading ? (
        <div className="text-center text-[12px] font-mono text-primary/50 py-20">LOADING ANALYTICS DATA...</div>
      ) : error ? (
        <div className="text-center text-[12px] font-mono text-status-alert py-20">{error}</div>
      ) : (
        <>
          {/* Chart 1 — Vehicles */}
          <div className="border border-border bg-panel p-4">
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-3">◻ MODULE 1: Vehicle Count</div>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradV" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="bucket" tick={DARK_LABEL_STYLE} axisLine={false} tickLine={false} />
                <YAxis tick={DARK_LABEL_STYLE} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="avg_vehicles" stroke="#38bdf8" fill="url(#gradV)" strokeWidth={2} name="Avg Vehicles" />
                <Area type="monotone" dataKey="max_vehicles" stroke="#38bdf8" fill="none" strokeDasharray="4 2" strokeWidth={1} strokeOpacity={0.4} name="Max Vehicles" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Chart 2 — People */}
          <div className="border border-border bg-panel p-4">
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-3">◉ MODULE 4: People Count</div>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradP" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#818cf8" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="bucket" tick={DARK_LABEL_STYLE} axisLine={false} tickLine={false} />
                <YAxis tick={DARK_LABEL_STYLE} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="avg_people" stroke="#818cf8" fill="url(#gradP)" strokeWidth={2} name="Avg People" />
                <Area type="monotone" dataKey="max_people" stroke="#818cf8" fill="none" strokeDasharray="4 2" strokeWidth={1} strokeOpacity={0.4} name="Max People" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Chart 3 — Zone Occupancy */}
          <div className="border border-border bg-panel p-4">
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-3">⬡ Zone Occupancy</div>
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradZ" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#fbbf24" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="bucket" tick={DARK_LABEL_STYLE} axisLine={false} tickLine={false} />
                <YAxis tick={DARK_LABEL_STYLE} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="avg_zone" stroke="#fbbf24" fill="url(#gradZ)" strokeWidth={2} name="Zone Occupancy" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* ANPR Records Table */}
          <div className="border border-border bg-panel p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">◻ MODULE 2: ANPR Records ({filteredPlates.length})</div>
              <input
                className="bg-background border border-border text-foreground text-[10px] font-mono px-2 py-1 w-48 outline-none focus:border-primary"
                placeholder="Search plate / vehicle..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] font-mono">
                <thead>
                  <tr className="border-b border-border/40">
                    {["PLATE", "VEHICLE TYPE", "CONFIDENCE", "FIRST SEEN", "LAST SEEN", "STATUS"].map(h => (
                      <th key={h} className="text-left py-1.5 px-2 text-muted-foreground uppercase tracking-widest font-normal">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredPlates.map((p, i) => (
                    <tr key={i} className={`border-b border-border/20 ${i % 2 === 0 ? "bg-white/[0.01]" : ""} hover:bg-primary/5 transition-colors`}>
                      <td className="py-1.5 px-2 text-foreground font-bold tracking-[0.15em]">{p.plate_text}</td>
                      <td className="py-1.5 px-2 text-muted-foreground">{p.vehicle_type}</td>
                      <td className="py-1.5 px-2">
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-muted/10 h-1.5">
                            <div className="h-full bg-primary transition-all" style={{ width: `${p.confidence * 100}%` }} />
                          </div>
                          <span className="text-foreground">{(p.confidence * 100).toFixed(1)}%</span>
                        </div>
                      </td>
                      <td className="py-1.5 px-2 text-muted-foreground">{p.first_seen}</td>
                      <td className="py-1.5 px-2 text-muted-foreground">{p.last_seen}</td>
                      <td className="py-1.5 px-2">
                        {(() => {
                          const status = p.status || (p.confidence >= 0.9 ? "CONFIRMED" : "PENDING");
                          return (
                            <span className={`text-[9px] px-1 py-0.5 border ${
                              status === "STOLEN" ? "border-status-alert/50 text-status-alert" :
                              status === "FLAGGED" ? "border-status-warning/50 text-status-warning" :
                              status === "CONFIRMED" ? "border-status-online/50 text-status-online" :
                              "border-status-warning/50 text-status-warning"
                            }`}>{status}</span>
                          );
                        })()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
