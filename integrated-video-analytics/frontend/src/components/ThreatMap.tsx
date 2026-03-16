import { useEffect, useState } from "react";

interface Incident {
  id: number;
  x: number;
  y: number;
  life: number;
}

export function ThreatMap() {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    const interval = setInterval(() => {
      // Add new incident
      if (Math.random() > 0.7) {
        setIncidents(prev => [
          ...prev.slice(-10),
          {
            id: Date.now(),
            x: Math.random() * 100,
            y: Math.random() * 100,
            life: 100
          }
        ]);
      }

      // Decay incidents
      setIncidents(prev => 
        prev
          .map(inc => ({ ...inc, life: inc.life - 2 }))
          .filter(inc => inc.life > 0)
      );
    }, 100);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-full h-full relative overflow-hidden bg-black/40 border border-border/20 group">
      {/* Grid Pattern */}
      <div 
        className="absolute inset-0 opacity-[0.1]" 
        style={{
          backgroundImage: `
            linear-gradient(hsl(var(--primary) / 0.3) 0.5px, transparent 0.5px),
            linear-gradient(90deg, hsl(var(--primary) / 0.3) 0.5px, transparent 0.5px)
          `,
          backgroundSize: "10px 10px",
        }}
      />

      {/* Map Outline Simulation (Simplified) */}
      <div className="absolute inset-0 opacity-10 flex items-center justify-center">
        <div className="w-[80%] h-[60%] border border-primary rounded-[40%] blur-[2px]" />
        <div className="w-[40%] h-[30%] border border-secondary rounded-full absolute blur-[4px]" />
      </div>

      {/* Incidents */}
      {incidents.map(inc => (
        <div 
          key={inc.id}
          className="absolute w-1 h-1 bg-status-alert rounded-full shadow-[0_0_8px_hsl(var(--status-alert))]"
          style={{ 
            left: `${inc.x}%`, 
            top: `${inc.y}%`, 
            opacity: inc.life / 100,
            transform: `scale(${1 + (100 - inc.life) / 50})`
          }}
        />
      ))}

      {/* Scanline */}
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-primary/5 to-transparent animate-h-scan pointer-events-none" />

      {/* HUD Info */}
      <div className="absolute top-1 left-1 flex flex-col gap-0.5">
        <div className="flex items-center gap-1">
          <div className="w-1 h-1 bg-primary animate-pulse" />
          <span className="text-[6px] font-mono text-primary/60 tracking-widest uppercase">Global_Sentry_Net</span>
        </div>
        <span className="text-[5px] font-mono text-muted-foreground/40 uppercase">Satellite_Uplink: Active</span>
      </div>

      <div className="absolute bottom-1 right-1 text-[5px] font-mono text-primary/40 uppercase">
        Ver: 0.9.4 // Map_Sim
      </div>
    </div>
  );
}
