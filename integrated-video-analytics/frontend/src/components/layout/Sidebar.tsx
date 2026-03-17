import { useState, useEffect } from "react";
import { Camera, BarChart2, Users, Network, Settings, ShieldAlert, PersonStanding } from "lucide-react";

export type ViewType = "live" | "analytics" | "watchlist" | "osint" | "weapons" | "persons" | "settings";

interface SidebarProps {
  activeView: ViewType;
  onNavigate: (view: ViewType) => void;
  systemHealth?: { cpu?: number; ram?: number; gpu?: number };
}

const navItems: {
  id: ViewType;
  label: string;
  icon: React.ComponentType<{ size?: string | number; className?: string }>;
  alert?: boolean;
  bottom?: boolean;
}[] = [
  { id: "live",      label: "LIVE VIEW",  icon: Camera },
  { id: "analytics", label: "ANALYTICS",  icon: BarChart2 },
  { id: "watchlist", label: "WATCHLIST",  icon: Users },
  { id: "osint",     label: "OSINT",      icon: Network },
  { id: "weapons",   label: "WEAPONS",    icon: ShieldAlert, alert: true },
  { id: "persons",   label: "PERSONS",    icon: PersonStanding },
  { id: "settings",  label: "SETTINGS",   icon: Settings, bottom: true },
];

export function Sidebar({ activeView, onNavigate, systemHealth }: SidebarProps) {
  const [expanded, setExpanded] = useState(false);
  const [collapseTimer, setCollapseTimer] = useState<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = () => {
    if (collapseTimer) clearTimeout(collapseTimer);
    setExpanded(true);
  };

  const handleMouseLeave = () => {
    const t = setTimeout(() => setExpanded(false), 300);
    setCollapseTimer(t);
  };

  const topItems = navItems.filter(i => !i.bottom);
  const bottomItems = navItems.filter(i => i.bottom);

  const activeIndex = topItems.findIndex(i => i.id === activeView);
  const indicatorTop = activeIndex >= 0 ? activeIndex * 48 : 0;

  return (
    <aside
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{
        width: expanded ? 200 : 52,
        transition: "width 200ms ease",
        gridColumn: "1 / 2",
        gridRow: "2 / 3",
      }}
      className="relative bg-panel border-r border-border flex flex-col overflow-hidden shrink-0"
    >
      {/* Active indicator bar */}
      <div
        className="absolute left-0 w-0.5 bg-primary transition-all duration-200"
        style={{ top: indicatorTop, height: 48 }}
      />

      {/* Top nav items */}
      <div className="flex flex-col flex-1">
        {topItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              style={{ height: 48, minHeight: 48 }}
              className={`flex items-center gap-3 px-3.5 w-full text-left transition-all ${
                isActive
                  ? item.alert ? "bg-status-alert/10 text-status-alert" : "bg-primary/8 text-primary"
                  : item.alert ? "text-status-alert/70 hover:bg-status-alert/10 hover:text-status-alert" : "text-muted-foreground hover:bg-border/50 hover:text-foreground"
              }`}
            >
              <Icon size={18} className="shrink-0" />
              {expanded && (
                <span className="text-[11px] font-sans font-medium uppercase tracking-wider whitespace-nowrap animate-sidebar-expand">
                  {item.label}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* System health (visible when expanded) */}
      {expanded && systemHealth && (
        <div className="px-3 py-2 border-t border-border animate-sidebar-expand">
          <div className="text-[8px] font-mono text-muted-foreground uppercase tracking-widest mb-1.5">SYSTEM</div>
          {[
            { label: "CPU", val: systemHealth.cpu ?? 0 },
            { label: "RAM", val: systemHealth.ram ?? 0 },
            { label: "GPU", val: systemHealth.gpu },
          ].map(({ label, val }) => (
            <div key={label} className="flex items-center gap-2 mb-1">
              <span className="text-[8px] font-mono text-muted-foreground w-6">{label}</span>
              <div className="flex-1 h-1 bg-border/60">
                {val != null && (
                  <div
                    className={`h-full transition-all duration-500 ${val > 80 ? "bg-status-alert" : val > 60 ? "bg-status-warning" : "bg-status-online"}`}
                    style={{ width: `${val}%` }}
                  />
                )}
              </div>
              <span className="text-[8px] font-mono text-muted-foreground w-6 text-right">
                {val != null ? `${val}%` : "N/A"}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Bottom items */}
      <div className="border-t border-border">
        {bottomItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              style={{ height: 48 }}
              className={`flex items-center gap-3 px-3.5 w-full text-left transition-all ${
                isActive
                  ? "bg-primary/8 text-primary"
                  : "text-muted-foreground hover:bg-border/50 hover:text-foreground"
              }`}
            >
              <Icon size={18} className="shrink-0" />
              {expanded && (
                <span className="text-[11px] font-sans font-medium uppercase tracking-wider whitespace-nowrap animate-sidebar-expand">
                  {item.label}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </aside>
  );
}
