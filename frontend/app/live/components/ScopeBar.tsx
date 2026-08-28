"use client";

interface ScopeBarProps {
  currentVerbs: number;
  maxVerbs?: number;
  verbNames?: string[];
  allVerbs?: string[];
  className?: string;
}

export function ScopeBar({
  currentVerbs,
  maxVerbs = 4,
  verbNames = [],
  allVerbs = [],
  className = "",
}: ScopeBarProps) {
  const safeMax = Math.max(1, maxVerbs);
  const clampedCurrent = Math.max(0, Math.min(currentVerbs, safeMax));
  const activeSet = new Set(verbNames.map((v) => v.toLowerCase()));

  return (
    <div className={`flex items-center gap-2 font-mono text-xs ${className}`}>
      <span className="text-slate select-none">scope</span>
      <div className="flex items-center gap-1" aria-label={`Scope: ${clampedCurrent} of ${safeMax} verbs active`}>
        {Array.from({ length: safeMax }).map((_, index) => {
          const isActive = index < clampedCurrent;
          const verb = allVerbs[index] || "";
          return (
            <div
              key={index}
              className={`w-3 h-3 rounded-xs transition-colors ${
                isActive
                  ? "bg-ledger-green shadow-xs shadow-ledger-green/30"
                  : "bg-slate/20 border border-slate/40"
              }`}
              title={verb ? (isActive ? `${verb} (active)` : `${verb} (removed)`) : undefined}
            />
          );
        })}
      </div>
      {verbNames.length > 0 ? (
        <span className="text-slate select-none">
          {"{"}
          {allVerbs.map((v, i) => {
            const isActive = activeSet.has(v.toLowerCase());
            return (
              <span key={v}>
                {i > 0 && ", "}
                <span className={isActive ? "text-ledger-green" : "text-slate/40 line-through"}>
                  {v}
                </span>
              </span>
            );
          })}
          {"}"}
        </span>
      ) : (
        <span className="text-slate select-none">
          {clampedCurrent} {clampedCurrent === 1 ? "verb" : "verbs"}
        </span>
      )}
    </div>
  );
}
