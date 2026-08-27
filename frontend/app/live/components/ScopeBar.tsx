"use client";

interface ScopeBarProps {
  currentVerbs: number;
  maxVerbs?: number;
  className?: string;
}

export function ScopeBar({
  currentVerbs,
  maxVerbs = 4,
  className = "",
}: ScopeBarProps) {
  const safeMax = Math.max(1, maxVerbs);
  const clampedCurrent = Math.max(0, Math.min(currentVerbs, safeMax));

  return (
    <div className={`flex items-center gap-2 font-mono text-xs ${className}`}>
      <span className="text-slate select-none">scope</span>
      <div className="flex items-center gap-1" aria-label={`Scope: ${clampedCurrent} of ${safeMax} verbs active`}>
        {Array.from({ length: safeMax }).map((_, index) => {
          const isActive = index < clampedCurrent;
          return (
            <div
              key={index}
              className={`w-3 h-3 rounded-xs transition-colors ${
                isActive
                  ? "bg-ledger-green shadow-xs shadow-ledger-green/30"
                  : "bg-slate/20 border border-slate/40"
              }`}
              title={isActive ? `Verb active (${index + 1}/${safeMax})` : `Verb attenuated/removed`}
            />
          );
        })}
      </div>
      <span className="text-slate select-none">
        {clampedCurrent} {clampedCurrent === 1 ? "verb" : "verbs"}
      </span>
    </div>
  );
}
