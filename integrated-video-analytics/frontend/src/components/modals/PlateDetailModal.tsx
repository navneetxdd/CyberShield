import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Search, Car, Calendar, MapPin, Database, ExternalLink } from "lucide-react";

interface PlateDetailModalProps {
  plate: any;
  open: boolean;
  onClose: () => void;
}

export function PlateDetailModal({ plate, open, onClose }: PlateDetailModalProps) {
  if (!plate) return null;

  const metadata = [
    { icon: <Search size={12} />, label: "PLATE TEXT", value: plate.plate_text, highlight: true },
    { icon: <Car size={12} />, label: "VEHICLE TYPE", value: plate.vehicle_type || "CAR" },
    { icon: <Calendar size={12} />, label: "FIRST DETECTED", value: plate.first_seen || "UNKNOWN" },
    { icon: <MapPin size={12} />, label: "LAST POSITION", value: plate.camera_id || "CAM_01" },
    { icon: <Database size={12} />, label: "DB STATUS", value: plate.status || "CLEARED" },
  ];

  const statusColor = plate.status === "STOLEN" ? "text-status-alert" : plate.status === "FLAGGED" ? "text-status-warning" : "text-status-online";

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-[800px] p-0 border-border bg-background rounded-none overflow-hidden font-mono shadow-[0_0_20px_rgba(0,0,0,0.5)]">
        <div className="flex flex-col h-[500px]">
          {/* Header */}
          <div className="px-6 py-4 border-b border-border bg-panel flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-1.5 h-1.5 rounded-full bg-primary glow-cyan" />
              <div className="text-[12px] font-bold tracking-[0.2em] text-primary uppercase">FORENSIC ANALYSIS // PLATE_{plate.plate_text}</div>
            </div>
          </div>

          <div className="flex-1 flex overflow-hidden">
            {/* Left: Metadata */}
            <div className="w-[320px] border-r border-border p-6 space-y-4 bg-panel/30">
              <div className="space-y-3">
                {metadata.map((item, idx) => (
                  <div key={idx} className="space-y-1">
                    <div className="flex items-center gap-2 text-[9px] text-muted-foreground uppercase tracking-wider">
                      {item.icon} {item.label}
                    </div>
                    <div className={`text-[13px] font-bold ${item.highlight ? 'text-primary' : 'text-foreground'}`}>
                      {item.value}
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-4 border-t border-border">
                <div className="text-[9px] text-muted-foreground uppercase mb-2">CRIMINAL JUSTICE DATASET (NCIC)</div>
                <div className={`text-[11px] font-bold uppercase p-2 border ${plate.status === "STOLEN" ? 'bg-status-alert/10 border-status-alert' : 'bg-status-online/5 border-status-online'} ${statusColor}`}>
                  {plate.status === "STOLEN" ? "● REGISTERED STOLEN // ARREST WARRANT ACTIVE" : "● NO ACTIVE WARRANTS // CLEARED"}
                </div>
              </div>

              <div className="flex flex-col gap-2 pt-4">
                <button className="w-full py-2 bg-primary/15 border border-primary/50 text-primary text-[10px] font-bold uppercase hover:bg-primary/25 transition-all flex items-center justify-center gap-2">
                  <Database size={12} /> SYNC TO CENTRAL COMMAND
                </button>
                <button className="w-full py-2 bg-panel border border-border text-muted-foreground text-[10px] font-bold uppercase hover:text-foreground hover:border-primary/40 transition-all flex items-center justify-center gap-2">
                  <ExternalLink size={12} /> EXTERNAL SEARCH
                </button>
              </div>
            </div>

            {/* Right: Snapshot & Crops */}
            <div className="flex-1 p-6 space-y-6 overflow-y-auto">
              <div>
                <div className="text-[10px] text-muted-foreground uppercase mb-3 flex justify-between">
                  <span>FORENSIC CAPTURE</span>
                  <span className="text-primary font-bold">CONFIDENCE: {(plate.confidence * 100).toFixed(1)}%</span>
                </div>
                <div className="relative group overflow-hidden border border-border">
                  <img src={plate.snapshot_url || plate.image || "https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?w=1200&auto=format&fit=crop&q=60"} 
                       className="w-full h-48 object-cover transition-transform duration-500 group-hover:scale-105" 
                       alt="Plate Frame" />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent pointer-events-none" />
                  <div className="absolute bottom-2 left-2 text-[9px] text-white/80">LATITUDE: 28.6139° N | LONGITUDE: 77.2090° E</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-[9px] text-muted-foreground uppercase mb-2">VEHICLE CROP</div>
                  <div className="h-24 bg-panel border border-border flex items-center justify-center overflow-hidden">
                    <img src={plate.vehicle_image || "https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?w=300&auto=format&fit=crop&q=60"} className="w-full h-full object-contain" />
                  </div>
                </div>
                <div>
                  <div className="text-[9px] text-muted-foreground uppercase mb-2">LICENSE PLATE CROP</div>
                  <div className="h-24 bg-white border border-border flex items-center justify-center p-2">
                    <div className="text-[24px] font-bold text-black border-2 border-black/80 px-4 py-1 flex flex-col items-center">
                      <span className="text-[8px] leading-none mb-1 font-mono">IND</span>
                      {plate.plate_text}
                    </div>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                 <div className="text-[9px] text-muted-foreground uppercase mb-2">OCR CONFIDENCE HEATMAP</div>
                 <div className="h-1 bg-border rounded-full overflow-hidden">
                    <div className="h-full bg-primary" style={{ width: '88%' }} />
                 </div>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
