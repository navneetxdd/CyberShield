import { useState } from "react";
import { AlertTriangle, Check, Info, Shield, User, X } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { apiAssetUrl, apiUpload } from "@/lib/api";
import { toast } from "sonner";

interface QuickEnrollModalProps {
  face: any;
  open: boolean;
  onClose: () => void;
}

export function QuickEnrollModal({ face, open, onClose }: QuickEnrollModalProps) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  const handleEnroll = async () => {
    if (!name.trim()) return;
    if (!/^[A-Za-z0-9_-]+$/.test(name)) {
      toast.error("Invalid name. Use letters, numbers, hyphens, and underscores only.");
      return;
    }

    const snapshotUrl = apiAssetUrl(face?.snapshot_url || face?.image);
    if (!snapshotUrl) {
      toast.error("No face snapshot is available for quick enrollment.");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(snapshotUrl);
      if (!response.ok) {
        throw new Error("Unable to fetch face snapshot.");
      }
      const blob = await response.blob();
      const imageFile = new File([blob], `${name}.jpg`, { type: blob.type || "image/jpeg" });

      const form = new FormData();
      form.append("name", name);
      form.append("file", imageFile);
      await apiUpload("/api/watchlist", form);

      toast.success(`Subject ${name} enrolled successfully.`);
      setName("");
      onClose();
    } catch (error: any) {
      toast.error(error?.message || "Enrollment failed.");
    } finally {
      setLoading(false);
    }
  };

  if (!face) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-[400px] p-0 border-border bg-background rounded-none overflow-hidden font-mono shadow-[0_0_30px_rgba(0,0,0,0.6)]">
        <div className="flex flex-col">
          <div className="px-5 py-3 border-b border-border bg-panel flex items-center gap-2">
            <Shield size={14} className="text-status-alert" />
            <span className="text-[10px] font-bold tracking-[0.1em] text-foreground uppercase">Quick Watchlist Enrollment</span>
          </div>

          <div className="p-6 space-y-6">
            <div className="flex gap-4">
              <div className="w-20 h-20 border border-border bg-panel flex items-center justify-center shrink-0 relative">
                {face.snapshot_url || face.image ? (
                  <img src={apiAssetUrl(face.snapshot_url || face.image)} className="w-full h-full object-cover" alt="Subject" />
                ) : (
                  <User size={32} className="text-muted-foreground/30" />
                )}
                <div className="absolute -bottom-2 -right-2 bg-status-alert text-white text-[8px] font-bold px-1 py-0.5">
                  CONF: {Math.round((face.confidence || 0.8) * 100)}%
                </div>
              </div>
              <div className="flex-1 space-y-2">
                <div className="text-[9px] text-muted-foreground uppercase flex items-center gap-1">
                  <Info size={10} /> Detection Metadata
                </div>
                <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                  <span className="text-[8px] text-muted-foreground uppercase leading-none">Gender</span>
                  <span className="text-[9px] text-foreground font-bold leading-none">{face.gender || "Unknown"}</span>
                  <span className="text-[8px] text-muted-foreground uppercase leading-none">Est. Age</span>
                  <span className="text-[9px] text-foreground font-bold leading-none">{face.age || "N/A"}</span>
                  <span className="text-[8px] text-muted-foreground uppercase leading-none">Detection</span>
                  <span className="text-[9px] text-foreground font-bold leading-none">{face.time || "Just now"}</span>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-[9px] text-muted-foreground uppercase tracking-widest pl-1">Assign Subject Identifier</label>
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value.toUpperCase().replace(/\s/g, "_"))}
                  placeholder="SUSPECT_ALPHA_01"
                  className="w-full bg-panel border-border text-foreground text-[12px] font-bold font-mono px-3 py-2 outline-none focus:border-primary transition-all uppercase"
                />
                <p className="text-[8px] text-muted-foreground">Unique alphanumeric ID required for forensic tracking.</p>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={onClose}
                  className="flex-1 flex items-center justify-center gap-2 py-2 border border-border text-[10px] font-bold uppercase text-muted-foreground hover:text-foreground hover:border-border/80 transition-all"
                >
                  <X size={12} /> Cancel
                </button>
                <button
                  disabled={!name || loading}
                  onClick={handleEnroll}
                  className="flex-1 flex items-center justify-center gap-2 py-2 bg-status-alert/15 border border-status-alert/50 text-status-alert text-[10px] font-bold uppercase hover:bg-status-alert/25 disabled:opacity-50 transition-all"
                >
                  {loading ? <span className="animate-pulse">Enrolling...</span> : <><Check size={12} /> Commit</>}
                </button>
              </div>
            </div>
          </div>

          <div className="px-5 py-3 border-t border-border bg-status-alert/5 flex items-start gap-3">
            <AlertTriangle size={14} className="text-status-alert shrink-0 mt-0.5" />
            <p className="text-[8px] text-status-alert/80 leading-relaxed uppercase">
              Legal notice: Watchlist enrollment triggers real-time facial matching across active feeds.
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
