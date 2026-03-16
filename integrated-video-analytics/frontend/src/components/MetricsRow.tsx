import { useEffect, useState } from "react";
import { CyberShieldState } from "../pages/Index";

interface SparklineProps {
  data: number[];
  color: string;
  width?: number;
  height?: number;
}

function Sparkline({ data, color, width = 100, height = 32 }: SparklineProps) {
  const max = Math.max(...data) || 10;
  const min = Math.min(...data) || 0;
  const range = max - min || 1;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  const areaPoints = `0,${height} ${points} ${width},${height}`;
  const lastY = height - ((data[data.length - 1] - min) / range) * (height - 4) - 2;
  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={`grad-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#grad-${color.replace("#", "")})`} />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" opacity="0.8" />
      <circle cx={width} cy={lastY || 0} r="2" fill={color} />
    </svg>
  );
}

function VehicleClassChart({ types }: { types: Record<string, number> }) {
  const cats = Object.entries(types || {}).map(([k, v]) => ({ label: k.toUpperCase(), value: v as number }));
  if (cats.length === 0) {
    cats.push({ label: "CAR", value: 5 }, { label: "TRUCK", value: 2 }, { label: "MOTORCYCLE", value: 1 });
  }
  const total = cats.reduce((s, c) => s + c.value, 0) || 1;
  const barColors = ["bg-primary", "bg-secondary", "bg-status-warning", "bg-muted-foreground", "bg-primary/50"];
  const hexColors = ["hsl(var(--primary))", "hsl(var(--secondary))", "hsl(var(--status-warning))", "hsl(var(--muted-foreground))"];

  return (
    <div className="border border-border bg-panel p-3 relative overflow-hidden flex flex-col justify-between col-span-2">
      <div className="text-[10px] font-mono tracking-[0.15em] uppercase text-muted-foreground mb-2 font-bold">◻ MODULE 1: Vehicle Classification</div>
      {/* Stacked bar */}
      <div className="flex h-3 mb-3 gap-px rounded-sm overflow-hidden">
        {cats.map((cat, i) => (
          <div key={cat.label} style={{ width: `${(cat.value / total) * 100}%`, backgroundColor: hexColors[i % hexColors.length] }} className="transition-all duration-500" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {cats.map((cat, i) => (
          <div key={cat.label} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 shrink-0 rounded-sm ${barColors[i % barColors.length]}`} />
            <span className="text-[10px] font-mono text-muted-foreground flex-1 truncate">{cat.label}</span>
            <span className="text-[10px] font-mono text-foreground font-bold">{cat.value}</span>
            <span className="text-[9px] font-mono text-muted-foreground/60">({Math.round((cat.value / total) * 100)}%)</span>
          </div>
        ))}
      </div>
      <div className="absolute top-0 right-0 w-4 h-4 border-t border-r border-primary/20" />
    </div>
  );
}

interface MetricsRowProps {
  state: CyberShieldState;
}

export function MetricsRow({ state }: MetricsRowProps) {
  const [history, setHistory] = useState<Record<string, number[]>>({
    VEH_COUNT: Array.from({ length: 25 }, () => 0),
    FPS_RATE: Array.from({ length: 25 }, () => 0),
    PEOPLE_COUNT: Array.from({ length: 25 }, () => 0),
    LATENCY_MS: Array.from({ length: 25 }, () => 0),
  });

  useEffect(() => {
    const interval = setInterval(() => {
      setHistory((prev) => {
        const next = { ...prev };
        const add = (k: string, val: number) => {
          const arr = [...(next[k] || []), val];
          if (arr.length > 25) arr.shift();
          next[k] = arr;
        };
        add("VEH_COUNT", state.vehicle_count);
        add("FPS_RATE", state.stream_fps);
        add("PEOPLE_COUNT", state.people_count);
        add("LATENCY_MS", state.inference_latency_ms);
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [state.vehicle_count, state.stream_fps, state.people_count, state.inference_latency_ms]);

  const metricConfigs = [
    { label: "VEH_COUNT", title: "◻ Vehicles", unit: "obj", color: "hsl(var(--tactical-gold))", desc: "Module 1" },
    { label: "FPS_RATE", title: "⚙ Stream FPS", unit: "fps", color: "hsl(var(--tactical-cyan))", desc: "Realtime" },
    { label: "PEOPLE_COUNT", title: "◉ Persons", unit: "obj", color: "hsl(var(--secondary))", desc: "Module 4" },
    { label: "LATENCY_MS", title: "⚡ Latency", unit: "ms", color: "hsl(var(--tactical-gold))", desc: "Inference" },
  ];

  return (
    <footer className="col-span-12 grid grid-cols-8 gap-2">
      {metricConfigs.map((m) => {
        const data = history[m.label] || [0];
        const currentValue = data[data.length - 1] ?? 0;
        const prevValue = data[data.length - 2] ?? 0;
        const delta = currentValue - prevValue;
        const isUp = delta >= 0;
        return (
          <div key={m.label} className="col-span-1 border border-border bg-panel p-3 relative overflow-hidden group hover:bg-white/[0.02] transition-colors">
            <div className="absolute top-0 left-0 w-3 h-3 border-t border-l border-primary/20 group-hover:border-primary" />
            <div className="text-[9px] font-mono tracking-widest uppercase text-muted-foreground mb-0.5">{m.desc}</div>
            <div className="text-[10px] font-mono tracking-[0.1em] uppercase text-primary/80 font-bold mb-1.5">{m.title}</div>
            <div className="flex items-end justify-between">
              <div>
                <div className="text-[22px] font-mono text-foreground tabular leading-none font-bold" style={{ textShadow: `0 0 10px ${m.color}` }}>
                  {currentValue.toFixed(m.unit === "fps" ? 1 : m.unit === "ms" ? 1 : 0)}
                </div>
                <div className="flex items-center gap-1 mt-1">
                  <span className="text-[9px] font-mono text-primary/60 uppercase">{m.unit}</span>
                  <span className={`text-[8px] font-mono tabular ${isUp ? "text-status-online" : "text-status-alert"}`}>
                    {isUp ? "▲" : "▼"}{Math.abs(delta).toFixed(1)}
                  </span>
                </div>
              </div>
              <Sparkline data={data} color={m.color} width={80} />
            </div>
            <div className="absolute bottom-0 left-0 w-full h-px" style={{ backgroundColor: m.color, opacity: 0.3 }} />
          </div>
        );
      })}
      <VehicleClassChart types={state.vehicle_types} />
      {/* ANPR + FRS Summary */}
      <div className="col-span-2 border border-border bg-panel p-3 relative overflow-hidden">
        <div className="text-[10px] font-mono tracking-widest uppercase text-muted-foreground mb-2 font-bold">◉ Module 2+3: ANPR / FRS</div>
        <div className="grid grid-cols-2 gap-2">
          {[
            ["Plates Read", (state.recent_plates || []).length, "hsl(var(--primary))"],
            ["Faces Matched", (state.recent_faces || []).length, "hsl(var(--secondary))"],
            ["WL Hits", (state.recent_faces || []).filter((f: any) => f.watchlist_hit).length, "hsl(var(--status-alert))"],
            ["Crowd Density", state.crowd_density || "N/A", "hsl(var(--status-warning))"],
          ].map(([label, val, color]) => (
            <div key={label as string} className="text-center border border-border/20 p-1.5">
              <div className="text-[16px] font-mono font-bold" style={{ color: color as string }}>{val}</div>
              <div className="text-[8px] font-mono text-muted-foreground uppercase truncate">{label}</div>
            </div>
          ))}
        </div>
        <div className="absolute top-0 right-0 w-4 h-4 border-t border-r border-primary/20" />
      </div>
      {/* System Health */}
      <div className="col-span-2 border border-border bg-panel p-3 relative overflow-hidden">
        <div className="text-[10px] font-mono tracking-widest uppercase text-muted-foreground mb-2 font-bold">⚙ System Health</div>
        <div className="space-y-1.5">
          {[
            ["GPU", (state as any).system_health?.gpu, "%", "bg-primary"],
            ["CPU", (state as any).system_health?.cpu, "%", "bg-secondary"],
            ["RAM", (state as any).system_health?.ram, "%", "bg-muted-foreground"],
          ].map(([label, val, unit, color]) => (
            <div key={label as string} className="flex items-center gap-2">
              <span className="text-[9px] font-mono text-muted-foreground w-6">{label}</span>
              <div className="flex-1 bg-muted/10 h-2 overflow-hidden">
                <div className={`h-full ${color} transition-all duration-1000`} style={{ width: `${Math.min(100, val || 0)}%` }} />
              </div>
              <span className="text-[9px] font-mono text-foreground font-bold w-10 text-right">{(val || 0).toFixed(0)}{unit}</span>
            </div>
          ))}
          <div className="flex justify-between text-[9px] font-mono text-muted-foreground mt-1">
            <span>GPU: {(state as any).system_health?.gpu_temp ?? "--"}°C</span>
            <span>CPU: {(state as any).system_health?.cpu_temp ?? "--"}°C</span>
            <span>Thr: {(state as any).system_health?.throughput ?? "--"} GB/s</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
