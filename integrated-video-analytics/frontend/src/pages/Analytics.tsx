import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "@/lib/api";
import { getConfig } from "@/lib/config";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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

interface AnalyticsProps {
  cameraId?: string;
}

export default function Analytics({ cameraId }: AnalyticsProps) {
  const [range, setRange] = useState<Range>("6H");
  const [history, setHistory] = useState<any[]>([]);
  const [plates, setPlates] = useState<any[]>([]);
  const [faces, setFaces] = useState<any[]>([]);
  const [vehicles, setVehicles] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    const limitByRange: Record<Range, number> = {
      "1H": 60,
      "6H": 360,
      "24H": 1440,
      "ALL": 5000,
    };
    const limit = limitByRange[range];
    const cameraQuery = cameraId ? `&camera_id=${encodeURIComponent(cameraId)}` : "";

    Promise.all([
      apiFetch(`/api/metrics?limit=${limit}${cameraQuery}`) as Promise<any>,
      apiFetch(`/api/analytics/summary?${cameraId ? `camera_id=${encodeURIComponent(cameraId)}` : ""}`) as Promise<any>,
      apiFetch(`/api/records/plates?limit=100${cameraQuery}`) as Promise<any>,
      apiFetch(`/api/records/faces?limit=100${cameraQuery}`) as Promise<any>,
      apiFetch(`/api/records/vehicles?limit=100${cameraQuery}`) as Promise<any>,
    ])
      .then(([metricsData, summaryData, plateData, faceData, vehicleData]) => {
        if (!active) return;
        const metrics = Array.isArray(metricsData?.history) ? metricsData.history : [];
        setHistory(metrics.map((item: any) => ({
          bucket: item.timestamp ? new Date(item.timestamp).toLocaleTimeString("en-GB", { hour12: false }) : "",
          vehicles: Number(item.vehicle_count || 0),
          people: Number(item.people_count || 0),
          zone: Number(item.zone_count || 0),
        })));
        setSummary(summaryData?.summary || null);
        setPlates(Array.isArray(plateData?.records) ? plateData.records : []);
        setFaces(Array.isArray(faceData?.records) ? faceData.records : []);
        setVehicles(Array.isArray(vehicleData?.records) ? vehicleData.records : []);
      })
      .catch(() => {
        if (!active) return;
        setError("Failed to load analytics from backend.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [cameraId, range]);

  const filteredPlates = useMemo(
    () => plates.filter((plate) => `${plate.plate_text} ${plate.vehicle_type}`.toLowerCase().includes(search.toLowerCase())),
    [plates, search],
  );
  const filteredFaces = useMemo(
    () => faces.filter((face) => `${face.identity || ""} ${face.gender || ""}`.toLowerCase().includes(search.toLowerCase())),
    [faces, search],
  );
  const filteredVehicles = useMemo(
    () => vehicles.filter((vehicle) => `${vehicle.vehicle_type || ""} ${vehicle.plate_text || ""}`.toLowerCase().includes(search.toLowerCase())),
    [vehicles, search],
  );

  const exportMaltego = async (entity: "faces" | "vehicles" | "plates" | "events") => {
    const config = getConfig();
    const qs = new URLSearchParams({
      entity,
      limit: "1000",
    });
    if (cameraId) qs.set("camera_id", cameraId);
    if (config.API_KEY) qs.set("api_key", config.API_KEY);
    const response = await fetch(`${config.API_URL}/api/export/maltego?${qs.toString()}`);
    const blob = await response.blob();
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = `maltego_${entity}_${Date.now()}.csv`;
    anchor.click();
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-mono p-4 space-y-4">
      <header className="flex items-center justify-between border border-border bg-panel px-4 py-2">
        <div className="flex items-center gap-4">
          <div className="w-2 h-2 bg-primary glow-cyan" />
          <span className="text-[12px] font-bold tracking-[0.2em] text-primary uppercase">CYBERSHIELD // ANALYTICS COMMAND</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {RANGES.map((item) => (
              <button
                key={item}
                onClick={() => setRange(item)}
                className={`px-3 py-1 text-[10px] font-mono uppercase tracking-widest border transition-all ${range === item ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-primary/30"}`}
              >
                {item}
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
          {summary && (
            <div className="grid grid-cols-5 gap-4">
              {[
                ["Vehicles", summary.total_vehicles],
                ["People", summary.total_people],
                ["Plates", summary.total_plates],
                ["Faces", summary.total_faces],
                ["Watchlist Hits", summary.watchlist_hits],
              ].map(([label, value]) => (
                <div key={label as string} className="border border-border bg-panel p-4">
                  <div className="text-[9px] font-mono text-muted-foreground uppercase">{label}</div>
                  <div className="text-[24px] font-mono text-foreground font-bold mt-2">{value as number}</div>
                </div>
              ))}
            </div>
          )}

          <div className="border border-border bg-panel p-4">
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mb-3">Realtime Metrics</div>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradV" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradP" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#818cf8" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="bucket" tick={DARK_LABEL_STYLE} axisLine={false} tickLine={false} />
                <YAxis tick={DARK_LABEL_STYLE} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="vehicles" stroke="#38bdf8" fill="url(#gradV)" strokeWidth={2} name="Vehicles" />
                <Area type="monotone" dataKey="people" stroke="#818cf8" fill="url(#gradP)" strokeWidth={2} name="People" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="border border-border bg-panel p-4 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">Historical Records</div>
              <div className="flex items-center gap-2">
                <input
                  className="bg-background border border-border text-foreground text-[10px] font-mono px-2 py-1 w-48 outline-none focus:border-primary"
                  placeholder="Search records..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                {(["plates", "faces", "vehicles", "events"] as const).map((entity) => (
                  <button
                    key={entity}
                    onClick={() => exportMaltego(entity)}
                    className="px-3 py-1 border border-border text-[9px] font-mono uppercase text-muted-foreground hover:text-foreground hover:border-primary/40 transition-all"
                  >
                    EXPORT {entity.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="border border-border/40">
                <div className="px-3 py-2 border-b border-border/40 text-[9px] font-mono text-muted-foreground uppercase">ANPR Records</div>
                <div className="max-h-[360px] overflow-auto">
                  <table className="w-full text-[10px] font-mono">
                    <tbody>
                      {filteredPlates.map((plate, index) => (
                        <tr key={`${plate.plate_text}-${index}`} className="border-b border-border/20">
                          <td className="px-3 py-2 text-foreground">{plate.plate_text}</td>
                          <td className="px-3 py-2 text-muted-foreground">{plate.vehicle_type}</td>
                          <td className="px-3 py-2 text-muted-foreground">{plate.last_seen}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="border border-border/40">
                <div className="px-3 py-2 border-b border-border/40 text-[9px] font-mono text-muted-foreground uppercase">Face Records</div>
                <div className="max-h-[360px] overflow-auto">
                  <table className="w-full text-[10px] font-mono">
                    <tbody>
                      {filteredFaces.map((face, index) => (
                        <tr key={`${face.camera_id}-${face.tracker_id}-${index}`} className="border-b border-border/20">
                          <td className="px-3 py-2 text-foreground">{face.identity || "Anonymous"}</td>
                          <td className="px-3 py-2 text-muted-foreground">{face.gender || "--"}</td>
                          <td className="px-3 py-2 text-muted-foreground">{face.watchlist_hit ? "WATCHLIST" : "OBSERVED"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="border border-border/40">
                <div className="px-3 py-2 border-b border-border/40 text-[9px] font-mono text-muted-foreground uppercase">Vehicle Records</div>
                <div className="max-h-[360px] overflow-auto">
                  <table className="w-full text-[10px] font-mono">
                    <tbody>
                      {filteredVehicles.map((vehicle, index) => (
                        <tr key={`${vehicle.camera_id}-${vehicle.tracker_id}-${index}`} className="border-b border-border/20">
                          <td className="px-3 py-2 text-foreground">{vehicle.vehicle_type}</td>
                          <td className="px-3 py-2 text-muted-foreground">{vehicle.plate_text || "--"}</td>
                          <td className="px-3 py-2 text-muted-foreground">{vehicle.last_seen}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
