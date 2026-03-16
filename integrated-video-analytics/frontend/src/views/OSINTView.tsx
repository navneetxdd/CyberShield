import { Network } from "lucide-react";

export function OSINTView() {
  return (
    <div className="h-full flex items-center justify-center flex-col gap-3">
      <Network size={48} className="text-muted-foreground/40" />
      <div className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">NO ENTITY CORRELATION DATA</div>
      <div className="text-[9px] font-sans text-muted-foreground/60 text-center max-w-xs">
        Start a stream and allow time for detections to accumulate.
        <br />(Graph builds automatically from co-occurring events)
      </div>
    </div>
  );
}
