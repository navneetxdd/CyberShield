import { useState } from "react";
import { Camera, AlertTriangle } from "lucide-react";
import { CyberShieldState } from "../../pages/Index";
import { CONFIG } from "../../lib/config";

interface CameraCellProps {
  cameraId: string;
  isActive: boolean;
  state?: Partial<CyberShieldState>;
  onClick: () => void;
}

export function CameraCell({ cameraId, isActive, state, onClick }: CameraCellProps) {
  const [imgError, setImgError] = useState(false);
  const streamUrl = `${CONFIG.API_URL}/api/video/stream/${cameraId}?api_key=${CONFIG.API_KEY}`;
  const density = state?.crowd_density || "Low";
  const densityColor = density === "High" ? "text-status-alert" : density === "Medium" ? "text-status-warning" : "text-status-online";

  return (
    <div
      onClick={onClick}
      className={`relative overflow-hidden border cursor-pointer transition-all duration-200 animate-feed-connect ${
        isActive ? "border-primary shadow-[0_0_8px_hsl(var(--primary)/0.3)]" : "border-border hover:border-primary/50 hover:shadow-[0_0_6px_hsl(var(--primary)/0.15)]"
      }`}
      style={{ aspectRatio: "16/9" }}
    >
      {imgError ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/80">
          <Camera size={24} className="text-muted-foreground/40 mb-1" />
          <span className="text-[9px] font-mono text-muted-foreground uppercase">FEED UNAVAILABLE</span>
        </div>
      ) : (
        <img
          src={streamUrl}
          className="w-full h-full object-cover"
          alt={`Stream ${cameraId}`}
          onError={() => setImgError(true)}
        />
      )}

      {/* Top-left: REC + FPS */}
      <div className="absolute top-1.5 left-1.5 flex items-center gap-1.5">
        <div className="flex items-center gap-1 bg-background/80 px-1.5 py-0.5">
          <div className="w-1.5 h-1.5 rounded-full bg-status-alert animate-pulse" />
          <span className="text-[8px] font-mono text-foreground">{cameraId}</span>
        </div>
        <div className="bg-background/80 px-1 py-0.5">
          <span className="text-[8px] font-mono text-muted-foreground">{state?.stream_fps?.toFixed(0) ?? "--"} FPS</span>
        </div>
      </div>

      {/* Top-right: Threat Level */}
      <div className="absolute top-1.5 right-1.5">
        <div className={`bg-background/80 px-1.5 py-0.5 text-[8px] font-mono uppercase ${densityColor}`}>
          {density.toUpperCase()}
        </div>
      </div>

      {/* Bottom-left: Counts */}
      <div className="absolute bottom-1.5 left-1.5 bg-background/80 px-1.5 py-0.5">
        <span className="text-[8px] font-mono text-foreground">
          🚗 {state?.vehicle_count ?? 0}  👤 {state?.people_count ?? 0}
        </span>
      </div>

      {/* Bottom-right: Latency */}
      <div className="absolute bottom-1.5 right-1.5 bg-background/80 px-1 py-0.5">
        <span className="text-[8px] font-mono text-muted-foreground">
          {Math.round(state?.inference_latency_ms ?? 0)}ms
        </span>
      </div>
    </div>
  );
}
