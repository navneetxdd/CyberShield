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

// Returns columns and rows so all cells (cameras + 1 placeholder) fit within the
// visible area without overflowing.  Rows use 1fr so height is distributed evenly.
function getGridLayout(cameraCount: number): { cols: number; rows: number } {
  const total = cameraCount + 1; // +1 for the "add feed" placeholder
  if (total <= 1) return { cols: 1, rows: 1 };
  if (total <= 2) return { cols: 2, rows: 1 };
  if (total <= 4) return { cols: 2, rows: 2 };
  if (total <= 6) return { cols: 3, rows: 2 };
  if (total <= 9) return { cols: 3, rows: 3 };
  return { cols: 4, rows: Math.ceil(total / 4) };
}

export function CameraGrid({ cameras, activeCamera, state, onSelectCamera, onAddFeed }: CameraGridProps) {
  if (cameras.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3">
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

  const { cols, rows } = getGridLayout(cameras.length);

  return (
    <div
      className="h-full p-2 gap-2"
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        gridTemplateRows: `repeat(${rows}, 1fr)`,
        // Allow vertical scroll only when there are so many feeds that rows
        // would be uncomfortably small (>9 cameras).
        overflowY: cameras.length > 9 ? "auto" : "hidden",
        overflowX: "hidden",
      }}
    >
      {cameras.map((id) => (
        <CameraCell
          key={id}
          cameraId={id}
          isActive={activeCamera === id}
          state={state}
          onClick={() => onSelectCamera(id)}
        />
      ))}

      {/* Add camera placeholder — fills its grid cell just like a CameraCell */}
      <div
        onClick={onAddFeed}
        className="border border-dashed border-border hover:border-primary/50 flex flex-col items-center justify-center cursor-pointer transition-all min-h-0"
      >
        <Plus size={24} className="text-muted-foreground/40 mb-1" />
        <span className="text-[9px] font-mono text-muted-foreground uppercase">ADD FEED</span>
      </div>
    </div>
  );
}
