import { useState, useEffect, useRef } from "react";
import { CyberShieldState } from "../pages/Index";
import { CONFIG } from "../lib/config";

function CornerBracket({ position }: { position: "tl" | "tr" | "bl" | "br" }) {
  const classes = {
    tl: "top-0 left-0 border-t-[3px] border-l-[3px]",
    tr: "top-0 right-0 border-t-[3px] border-r-[3px]",
    bl: "bottom-0 left-0 border-b-[3px] border-l-[3px]",
    br: "bottom-0 right-0 border-b-[3px] border-r-[3px]",
  };
  return (
    <div className={`absolute w-10 h-10 border-primary/60 z-10 animate-bracket-pulse ${classes[position]}`}>
      <div className={`absolute w-1.5 h-1.5 bg-primary/40 ${position.includes('t') ? 'top-0' : 'bottom-0'} ${position.includes('l') ? 'left-0' : 'right-0'}`} />
    </div>
  );
}

interface VideoPlayerProps {
  activeCamera: string;
  state: CyberShieldState;
  videoFlash?: boolean;
}

export function VideoPlayer({ activeCamera, state, videoFlash }: VideoPlayerProps) {
  const [frameCount, setFrameCount] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);

  // Crowd density overlay color (B4.4)
  const crowdOverlay = (() => {
    const zc = state.zone_count || 0;
    const d = (state.crowd_density || "").toLowerCase();
    if (d === "high" || zc > 7) return "rgba(239,68,68,0.12)";
    if (d === "medium" || zc >= 3) return "rgba(251,191,36,0.08)";
    return null;
  })();

  // Frame counter purely for aesthetics since the real backend video is MJPEG
  useEffect(() => {
    const interval = setInterval(() => setFrameCount((p) => p + 1), 33);
    return () => clearInterval(interval);
  }, []);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [state.event_logs]);

  // Construct absolute URL mapping to FastApi with security token
  const streamUrl = `${CONFIG.API_URL}/api/video/stream/${activeCamera}?api_key=${CONFIG.API_KEY}`;

  return (
    <main className={`w-full h-full relative border bg-background overflow-hidden flex items-center justify-center transition-all duration-300 ${
      videoFlash ? "border-status-alert ring-2 ring-status-alert" : "border-border"
    }`}>
      <CornerBracket position="tl" />
      <CornerBracket position="tr" />
      <CornerBracket position="bl" />
      <CornerBracket position="br" />

      {/* Main Video Source (OpenCV MJPEG) */}
      {activeCamera ? (
        <img 
          src={streamUrl} 
          className="w-full h-full object-contain absolute inset-0 z-0 opacity-90"
          alt="Video Stream"
        />
      ) : (
        <div className="flex flex-col items-center opacity-40 z-10">
            <svg className="w-16 h-16 text-muted-foreground mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 10l4.55-2.28A1 1 0 0121 8.62v6.76a1 1 0 01-1.45.89L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
            </svg>
            <p className="text-sm font-mono tracking-[0.2em] uppercase">Awaiting Feed Integration</p>
        </div>
      )}

      {/* Crowd Density Heat Overlay (B4.4) */}
      {crowdOverlay && (
        <div
          className="absolute inset-0 pointer-events-none z-5 transition-all duration-500"
          style={{
            background: crowdOverlay,
            animation: (state.crowd_density || "").toLowerCase() === "high" ? "densityPulse 1.5s ease-in-out infinite alternate" : undefined
          }}
        />
      )}

      {/* Tactical grid background overlay */}
      <div className="absolute inset-0 bg-background/5 pointer-events-none z-10">
        <div
          className="absolute inset-0 opacity-[0.2]"
          style={{
            backgroundImage: `
              linear-gradient(hsl(var(--primary) / 0.3) 1px, transparent 1px),
              linear-gradient(90deg, hsl(var(--primary) / 0.3) 1px, transparent 1px)
            `,
            backgroundSize: "32px 32px",
          }}
        />
        {/* Faint radar-like circle */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[60%] aspect-square border border-primary/[0.1] rounded-full" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[30%] aspect-square border border-primary/[0.15] rounded-full" />
      </div>

      {/* Vertical scan line */}
      <div className="absolute inset-0 pointer-events-none z-20 overflow-hidden">
        <div className="w-full h-12 bg-gradient-to-b from-transparent via-primary/10 to-transparent animate-scan" />
      </div>

      {/* Horizontal scan line */}
      <div className="absolute inset-0 pointer-events-none z-20 overflow-hidden">
        <div className="absolute top-0 h-full w-px bg-gradient-to-b from-transparent via-primary/20 to-transparent animate-h-scan" />
      </div>

      {/* HUD Overlays */}
      <div className="absolute inset-0 pointer-events-none z-30">
        {/* Top left telemetry */}
        <div className="absolute top-5 left-5 space-y-1">
          <div className="flex items-center gap-2 bg-background/80 backdrop-blur-sm px-2 py-0.5 border-l border-destructive shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <div className={`w-1.5 h-1.5 ${activeCamera ? "bg-destructive animate-pulse" : "bg-muted-foreground"}`} />
            <span className="text-[11px] font-mono text-foreground tracking-wider uppercase font-bold">
              {activeCamera ? "REC // 1080P_OPENCV" : "NO ACTIVE FEED"}
            </span>
          </div>
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-l border-primary/30 shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <span className="text-[9px] font-mono text-muted-foreground tracking-wider">
              FRM: <span className="text-primary tabular">{String(frameCount).padStart(8, "0")}</span>
            </span>
          </div>
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-l border-primary/30 shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <span className="text-[9px] font-mono text-muted-foreground tracking-wider">
              PRC: <span className={state.is_processing ? "text-status-online" : "text-primary"}>
                {state.is_processing ? "ANALYZING" : "STANDBY"}
              </span>
            </span>
          </div>
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-l border-primary/30 shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <span className="text-[9px] font-mono text-muted-foreground tracking-wider">
              OBJ: <span className="text-primary tabular">{state.vehicle_count + state.people_count}</span> TRACKED
            </span>
          </div>
          {/* Elite Hardware Telemetry */}
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-l border-status-online/40 shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <span className="text-[9px] font-mono text-muted-foreground tracking-wider">
              THR: <span className="text-status-online tabular">{(state as any).system_health?.throughput ?? 0.0} GB/S</span>
            </span>
          </div>
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-l border-status-warning/40 shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <span className="text-[9px] font-mono text-muted-foreground tracking-wider">
              TMP: <span className="text-status-warning tabular">{(state as any).system_health?.gpu_temp ?? 0}°C</span> GPU // <span className="text-status-warning tabular">{(state as any).system_health?.cpu_temp ?? 0}°C</span> CPU
            </span>
          </div>
        </div>

        {/* Top right - feed label */}
        <div className="absolute top-5 right-5 text-right space-y-1">
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-r border-primary inline-block shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <span className="text-[11px] font-mono text-primary tracking-widest font-bold">
              {activeCamera ? activeCamera : "NO_FEED"}
            </span>
          </div>
          <br/>
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-r border-muted inline-block shadow-[0_0_10px_rgba(0,0,0,0.5)] mt-1">
            <span className="text-[9px] font-mono text-muted-foreground tracking-wider">CYBERSHIELD_ANALYTICS</span>
          </div>
        </div>

        {/* Center crosshair Elite */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 opacity-40">
          <div className="relative">
            <div className="w-16 h-px bg-primary/40 absolute top-0 left-1/2 -translate-x-1/2 shadow-[0_0_8px_hsl(var(--primary))]" />
            <div className="h-16 w-px bg-primary/40 absolute top-1/2 left-0 -translate-y-1/2 ml-[31px] shadow-[0_0_8px_hsl(var(--primary))]" />
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-px bg-secondary/20 animate-h-scan" />
            <div className="w-6 h-6 border border-primary/30 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
            <div className="w-4 h-4 border-l border-t border-primary absolute top-1/2 left-1/2 -translate-x-[150%] -translate-y-[150%]" />
            <div className="w-4 h-4 border-r border-b border-primary absolute top-1/2 left-1/2 translate-x-[50%] translate-y-[50%]" />
            <div className="absolute -top-12 -left-12 text-[7px] font-mono text-primary/40 flex flex-col items-center">
              <span>HDG. 342.1</span>
              <span>VER. 0.04°</span>
            </div>
          </div>
        </div>

        {/* Privacy Compliance Indicator (B3.1) */}
        <div className="absolute bottom-5 left-5 mb-20 pointer-events-none">
          <div className="flex items-center gap-1 bg-background/80 backdrop-blur-sm px-2 py-0.5 border-l border-status-online/40">
            <span className="text-[8px] font-mono text-status-online tracking-wider">🔒 PRIVACY MODE: ACTIVE — NON-WATCHLIST FACES ANONYMIZED</span>
          </div>
        </div>

        {/* Bottom center — density label (B4.4) */}
        {crowdOverlay && (
          <div className="absolute bottom-24 left-1/2 -translate-x-1/2 pointer-events-none">
            <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 text-[9px] font-mono text-status-warning tracking-widest">
              DENSITY: {(state.crowd_density || "LOW").toUpperCase()} // ZONE: {state.zone_count || 0} IN FRAME
            </div>
          </div>
        )}

        {/* Bottom left - system log */}
        <div className="absolute bottom-5 left-5 w-72 pointer-events-auto">
          <div className="bg-background/90 backdrop-blur-md border border-border/50 p-1.5 shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <div className="text-[8px] font-mono text-muted-foreground tracking-widest mb-1 border-b border-border/50 pb-1">
              SYS_LOG // REALTIME
            </div>
            <div ref={logRef} className="h-16 overflow-y-auto space-y-0.5 pr-2">
              {state.event_logs && state.event_logs.length > 0 ? state.event_logs.map((entry, i) => (
                <div key={i} className={`text-[8px] font-mono tracking-wider flex gap-2 ${
                  entry.type.includes("Alert") ? "text-status-alert" : entry.type.includes("Warn") ? "text-status-warning" : "text-muted-foreground"
                } ${i === state.event_logs.length - 1 ? "animate-card-slide" : ""}`}>
                  <span className="text-muted-foreground/50 tabular shrink-0">{entry.time}</span>
                  <span className="truncate">{entry.type}: {entry.detail}</span>
                </div>
              )) : (
                <div className="text-[8px] font-mono text-muted-foreground/50 italic tracking-widest text-center mt-4">NO_LOG_DATA</div>
              )}
            </div>
          </div>
        </div>

        {/* Bottom right timestamp Elite */}
        <div className="absolute bottom-5 right-5 text-right space-y-1">
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-r border-primary/30 shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <span className="text-[9px] font-mono text-muted-foreground tabular tracking-wider uppercase">
              CYBER_SHIELD_V4.2.0 // ELITE_CORE
            </span>
          </div>
          <div className="bg-background/80 backdrop-blur-sm px-2 py-0.5 border-r border-primary/30 shadow-[0_0_10px_rgba(0,0,0,0.5)]">
            <span className="text-[9px] font-mono text-primary tabular tracking-widest uppercase">
              {new Date().toISOString().replace("T", " // ").split(".")[0]}
            </span>
          </div>
        </div>
      </div>
    </main>
  );
}
