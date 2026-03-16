import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Bell, AlertTriangle, User, Car, Clock, ChevronRight } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

interface AlertHistoryPopoverProps {
  alerts: any[];
  children: React.ReactNode;
}

export function AlertHistoryPopover({ alerts, children }: AlertHistoryPopoverProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        {children}
      </PopoverTrigger>
      <PopoverContent className="w-96 p-0 border-border bg-background rounded-none shadow-[0_0_30px_rgba(0,0,0,0.6)] font-mono">
        <div className="flex flex-col max-h-[500px]">
          {/* Header */}
          <div className="px-4 py-3 border-b border-border bg-panel flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <Bell size={14} className="text-primary" />
              <span className="text-[11px] font-bold tracking-[0.1em] text-foreground uppercase">ALERT REPOSITORY</span>
            </div>
            <span className="text-[9px] bg-status-alert px-2 py-0.5 text-white font-bold">{alerts.length} NEW</span>
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto scrollbar-hide">
            {alerts.length === 0 ? (
              <div className="py-20 text-center space-y-2">
                <Bell size={32} className="mx-auto text-muted-foreground/30" />
                <div className="text-[10px] text-muted-foreground uppercase">NO ACTIVE ALERTS</div>
              </div>
            ) : (
              alerts.map((alert, idx) => {
                const isWatchlist = alert.type?.includes("Watchlist");
                const Icon = isWatchlist ? User : alert.type?.includes("Vehicle") ? Car : AlertTriangle;
                
                return (
                  <div key={idx} className="group flex items-start gap-4 p-4 border-b border-border/40 hover:bg-white/[0.02] cursor-pointer transition-all">
                    <div className={`mt-1 h-10 w-10 shrink-0 border flex items-center justify-center ${isWatchlist ? 'border-status-alert bg-status-alert/10' : 'border-primary/30 bg-primary/5'}`}>
                      <Icon size={18} className={isWatchlist ? "text-status-alert" : "text-primary"} />
                    </div>
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex justify-between items-start">
                        <span className={`text-[10px] font-bold uppercase truncate ${isWatchlist ? 'text-status-alert' : 'text-primary'}`}>
                          {alert.type}
                        </span>
                        <div className="flex items-center gap-1 text-[8px] text-muted-foreground">
                          <Clock size={8} />
                          {alert.time}
                        </div>
                      </div>
                      <p className="text-[11px] text-foreground leading-snug line-clamp-2">
                        {alert.detail}
                      </p>
                      <div className="flex items-center justify-between pt-1">
                        <span className="text-[8px] text-muted-foreground uppercase">{alert.camera_id || "SYS"} // SECTOR_04</span>
                        <ChevronRight size={12} className="text-muted-foreground group-hover:text-primary transition-colors translate-x-1 opacity-0 group-hover:opacity-100 group-hover:translate-x-0" />
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="p-3 border-t border-border bg-panel shrink-0">
             <button className="w-full py-2 border border-border text-[9px] font-bold uppercase text-muted-foreground hover:text-foreground hover:border-primary/50 transition-all">
                ARCHIVE ALL NOTIFICATIONS
             </button>
          </div>
        </div>
      </PopoverContent>
 popover    </Popover>
  );
}
