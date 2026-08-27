"use client";

import type { BlastRadiusData } from "../../types";

interface BlastRadiusPanelProps {
  blastRadius: BlastRadiusData | null;
  isAttacking: boolean;
}

export function BlastRadiusPanel({ blastRadius, isAttacking }: BlastRadiusPanelProps) {
  return (
    <div className="border border-slate/30 rounded-lg bg-ink p-4 font-mono text-xs flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between border-b border-slate/20 pb-2 mb-3">
          <span className="text-slate font-sans uppercase tracking-wider text-[11px] font-semibold">
            Blast Radius
          </span>
          {blastRadius && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                blastRadius.max_sensitivity === "HIGH" || blastRadius.max_sensitivity === "CRITICAL"
                  ? "text-ledger-red bg-ledger-red/10 border border-ledger-red/30"
                  : blastRadius.max_sensitivity === "MEDIUM"
                  ? "text-seal-amber bg-seal-amber/10 border border-seal-amber/30"
                  : "text-ledger-green bg-ledger-green/10 border border-ledger-green/30"
              }`}
            >
              {blastRadius.max_sensitivity} IMPACT
            </span>
          )}
        </div>

        {isAttacking && !blastRadius ? (
          <div className="py-8 text-center space-y-2">
            <div className="inline-block w-4 h-4 border-2 border-slate/40 border-t-seal-amber rounded-full animate-spin" />
            <p className="text-slate text-xs animate-pulse">Simulating blast radius...</p>
          </div>
        ) : !blastRadius ? (
          <div className="py-10 text-center text-slate/70 italic space-y-1">
            <p className="text-sm">🛡</p>
            <p>(no attack detected)</p>
          </div>
        ) : (
          <div className="space-y-3.5">
            {/* Score Metric and Bar */}
            <div>
              <div className="flex justify-between items-baseline mb-1">
                <span className="text-slate">SCORE:</span>
                <span className="text-sm font-bold text-parchment">{blastRadius.score}</span>
              </div>
              <div className="w-full h-2.5 bg-slate/20 rounded-xs overflow-hidden border border-slate/30">
                <div
                  className={`h-full transition-all duration-500 rounded-xs ${
                    blastRadius.max_sensitivity === "HIGH" || blastRadius.max_sensitivity === "CRITICAL"
                      ? "bg-ledger-red"
                      : blastRadius.max_sensitivity === "MEDIUM"
                      ? "bg-seal-amber"
                      : "bg-ledger-green"
                  }`}
                  style={{ width: `${Math.min(100, Math.max(5, (blastRadius.score / 50) * 100))}%` }}
                />
              </div>
            </div>

            {/* Reachable Agent & Exposed Tool Counts */}
            <div className="grid grid-cols-2 gap-2 text-xs py-1 border-y border-slate/15">
              <div>
                <span className="text-slate">Reachable agents: </span>
                <span className="text-parchment font-semibold">{blastRadius.reachable_agent_count}</span>
              </div>
              <div>
                <span className="text-slate">Exposed tools: </span>
                <span className="text-parchment font-semibold">{blastRadius.exposed_tool_count}</span>
              </div>
            </div>

            {/* Sensitivity Breakdown */}
            {blastRadius.sensitivity_breakdown && (
              <div className="p-2.5 bg-ink/70 border border-slate/25 rounded space-y-1.5">
                <span className="text-[10px] uppercase font-sans text-slate tracking-wider block">
                  Sensitivity Breakdown
                </span>
                {["HIGH", "MEDIUM", "LOW"].map((level) => {
                  const count = blastRadius.sensitivity_breakdown[level] || 0;
                  const total = blastRadius.exposed_tool_count || 1;
                  const pct = Math.round((count / total) * 100);
                  const color =
                    level === "HIGH"
                      ? "bg-ledger-red text-ledger-red"
                      : level === "MEDIUM"
                      ? "bg-seal-amber text-seal-amber"
                      : "bg-ledger-green text-ledger-green";

                  return (
                    <div key={level} className="flex items-center gap-2 text-[11px]">
                      <span className="w-14 text-slate">{level}</span>
                      <div className="flex-1 h-1.5 bg-slate/20 rounded-xs overflow-hidden">
                        <div
                          className={`h-full ${color.split(" ")[0]}`}
                          style={{ width: count > 0 ? `${Math.max(8, pct)}%` : "0%" }}
                        />
                      </div>
                      <span className="text-parchment shrink-0 w-12 text-right">
                        {count} tool{count === 1 ? "" : "s"}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Exposed tools list */}
            {blastRadius.exposed_tools && blastRadius.exposed_tools.length > 0 && (
              <div className="space-y-1 pt-1">
                <span className="text-[10px] uppercase font-sans text-slate tracking-wider block">
                  Would have exposed:
                </span>
                <ul className="space-y-1 max-h-32 overflow-y-auto pr-1">
                  {blastRadius.exposed_tools.map((tool, idx) => (
                    <li key={idx} className="text-slate text-[11px] flex items-center justify-between gap-1">
                      <span className="text-parchment truncate">• {tool}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
