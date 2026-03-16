import { Plus } from "lucide-react";
import { CyberShieldState } from "../../pages/Index";
import { CameraCell } from "./CameraCell";

interface CameraGridProps {
  cameras: string[];
  activeCamera: string;
  state: CyberShieldState;
  onSelectCamera: (id: string) => void;
  onAddFeed: () => void;
}

function getGridCols(count: number): string {
  if (count === 1) return "grid-cols-1";
  if (count === 2) return "grid-cols-2";
  if (count <= 4) return "grid-cols-2";
  if (count <= 6) return "grid-cols-3";
  return "grid-cols-4";
}

export function CameraGrid({ cameras, activeCamera, state, onSelectCamera, onAddFeed }: CameraGridProps) {
  if (cameras.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3">
        <div className="w-16 h-16 border border-border/40 flex items-center justify-center">
          <Plus size={32} className="text-muted-foreground/40" />
        </div>
        <div className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">NO FEEDS CONNECTED</div>
        <div className="text-[9px] font-mono text-muted-foreground/60 text-center max-w-xs">
          Click ADD FEED in the top bar to connect a camera or upload a video recording.
        </div>
        <button
          onClick={onAddFeed}
          className="mt-2 px-4 py-2 bg-primary/15 border border-primary/50 text-primary text-[9px] font-mono uppercase tracking-wider hover:bg-primary/25 transition-all"
        >
          + ADD FIRST FEED
        </button>
      </div>
    );
  }

  return (
    <div className={`flex-1 p-2 grid ${getGridCols(cameras.length)} gap-2 overflow-auto content-start`}>
      {cameras.map((id) => (
        <CameraCell
          key={id}
          cameraId={id}
          isActive={activeCamera === id}
          state={state}
          onClick={() => onSelectCamera(id)}
        />
      ))}

      {/* Add camera placeholder */}
      <div
        onClick={onAddFeed}
        className="border border-dashed border-border hover:border-primary/50 flex flex-col items-center justify-center cursor-pointer transition-all"
        style={{ aspectRatio: "16/9" }}
      >
        <Plus size={24} className="text-muted-foreground/40 mb-1" />
        <span className="text-[9px] font-mono text-muted-foreground uppercase">ADD FEED</span>
      </div>
    </div>
  );
}
