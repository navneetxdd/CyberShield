import { useMemo } from "react";

interface CrowdDensityGaugeProps {
  peopleCount: number;
  crowdDensity: string;
  peopleTotalCount: number;
  zoneCount: number;
  genderStats: Record<string, number>;
}

export function CrowdDensityGauge({
  peopleCount, crowdDensity, peopleTotalCount, zoneCount, genderStats
}: CrowdDensityGaugeProps) {
  // Map density to needle angle (degrees from left, 0-180)
  const needleAngle = useMemo(() => {
    const density = crowdDensity?.toLowerCase() || "low";
    if (density === "high") return 150;
    if (density === "medium") return 90;
    return 30;
  }, [crowdDensity]);

  // SVG arc helper
  function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
    const toRad = (d: number) => (d * Math.PI) / 180;
    const x1 = cx + r * Math.cos(toRad(startAngle));
    const y1 = cy + r * Math.sin(toRad(startAngle));
    const x2 = cx + r * Math.cos(toRad(endAngle));
    const y2 = cy + r * Math.sin(toRad(endAngle));
    return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`;
  }

  const cx = 100, cy = 90, r = 70;
  const totalMale = genderStats?.Man || genderStats?.Male || 0;
  const totalFemale = genderStats?.Woman || genderStats?.Female || 0;
  const totalUnknown = genderStats?.Unknown || 0;
  const totalGendered = totalMale + totalFemale + totalUnknown || 1;

  const maleW = (totalMale / totalGendered) * 100;
  const femaleW = (totalFemale / totalGendered) * 100;
  const unknownW = (totalUnknown / totalGendered) * 100;

  const densityColor =
    crowdDensity === "High" ? "#ef4444" : crowdDensity === "Medium" ? "#fbbf24" : "#22c55e";

  return (
    <div className="border border-border bg-panel p-2 space-y-2">
      <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest text-center">⬡ CROWD ANALYTICS</div>

      {/* Gauge */}
      <div className="flex justify-center">
        <svg width="200" height="110" viewBox="0 0 200 110">
          {/* Background arcs */}
          <path d={describeArc(cx, cy, r, 180, 242)} stroke="#166534" strokeWidth="14" fill="none" strokeLinecap="butt" />
          <path d={describeArc(cx, cy, r, 242, 298)} stroke="#92400e" strokeWidth="14" fill="none" strokeLinecap="butt" />
          <path d={describeArc(cx, cy, r, 298, 360)} stroke="#7f1d1d" strokeWidth="14" fill="none" strokeLinecap="butt" />

          {/* Active density indicator */}
          <circle cx={cx + r * Math.cos((needleAngle * Math.PI) / 180 + Math.PI)} cy={cy + r * Math.sin((needleAngle * Math.PI) / 180 + Math.PI)} r="6" fill={densityColor} />

          {/* Needle */}
          <line
            x1={cx} y1={cy}
            x2={cx + (r - 15) * Math.cos(((needleAngle - 180) * Math.PI) / 180)}
            y2={cy + (r - 15) * Math.sin(((needleAngle - 180) * Math.PI) / 180)}
            stroke={densityColor}
            strokeWidth="2.5"
            strokeLinecap="round"
            style={{ transition: "all 0.8s ease" }}
          />
          <circle cx={cx} cy={cy} r="5" fill="#1a1a2e" stroke={densityColor} strokeWidth="1.5" />

          {/* Center text */}
          <text x={cx} y={cy + 22} textAnchor="middle" fill="#f1f5f9" fontFamily="monospace" fontSize="20" fontWeight="bold">
            {peopleCount}
          </text>
          <text x={cx} y={cy + 35} textAnchor="middle" fill={densityColor} fontFamily="monospace" fontSize="8" letterSpacing="2">
            {(crowdDensity || "LOW").toUpperCase()}
          </text>
        </svg>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-1 text-center">
        <div className="border border-border/40 py-1">
          <div className="text-[11px] font-mono font-bold text-foreground">{peopleTotalCount}</div>
          <div className="text-[8px] font-mono text-muted-foreground uppercase">SESSION TOTAL</div>
        </div>
        <div className="border border-border/40 py-1">
          <div className="text-[11px] font-mono font-bold text-foreground">{zoneCount}</div>
          <div className="text-[8px] font-mono text-muted-foreground uppercase">ZONE OCC.</div>
        </div>
      </div>

      {/* Gender bar (B4.2) */}
      <div>
        <div className="text-[8px] font-mono text-muted-foreground uppercase tracking-widest mb-1">Gender Classification</div>
        <div className="flex h-3 w-full overflow-hidden" style={{ borderRadius: 0 }}>
          {maleW > 0 && (
            <div className="bg-blue-600 flex items-center justify-center overflow-hidden transition-all duration-500"
              style={{ width: `${maleW}%`, transition: "width 0.5s ease" }}>
              {maleW > 20 && <span className="text-[7px] font-mono text-white truncate px-0.5">MAN: {totalMale}</span>}
            </div>
          )}
          {femaleW > 0 && (
            <div className="bg-pink-500 flex items-center justify-center overflow-hidden transition-all duration-500"
              style={{ width: `${femaleW}%`, transition: "width 0.5s ease" }}>
              {femaleW > 20 && <span className="text-[7px] font-mono text-white truncate px-0.5">WOMAN: {totalFemale}</span>}
            </div>
          )}
          {unknownW > 0 && (
            <div className="bg-gray-600 flex items-center justify-center overflow-hidden transition-all duration-500"
              style={{ width: `${unknownW}%`, transition: "width 0.5s ease" }}>
              {unknownW > 20 && <span className="text-[7px] font-mono text-white truncate px-0.5">?{totalUnknown}</span>}
            </div>
          )}
        </div>
        <div className="text-[8px] font-mono text-muted-foreground mt-1 text-center">
          ♂ {totalMale}  ♀ {totalFemale}  ? {totalUnknown}
        </div>
      </div>
    </div>
  );
}
