"use client";

import type { AttackObjective, AttackResultData } from "../../types";

interface RedTeamPanelProps {
  objectives: AttackObjective[];
  selectedObjectiveId: string;
  onSelectObjective: (id: string) => void;
  onLaunchAttack: () => void;
  isAttacking: boolean;
  attackResult: AttackResultData | null;
}

export function RedTeamPanel({
  objectives,
  selectedObjectiveId,
  onSelectObjective,
  onLaunchAttack,
  isAttacking,
  attackResult,
}: RedTeamPanelProps) {
  const isBlocked = attackResult?.verdict === "blocked";

  return (
    <div className="border border-slate/30 rounded-lg bg-ink p-4 font-mono text-xs space-y-3">
      {/* Controls row */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3 flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-gemma-purple font-semibold font-sans uppercase tracking-wider text-xs shrink-0">
            <span>⚔</span>
            <span>Red Team</span>
          </div>

          <select
            value={selectedObjectiveId}
            onChange={(e) => onSelectObjective(e.target.value)}
            disabled={isAttacking || objectives.length === 0}
            className="flex-1 min-w-[200px] max-w-md px-3 py-1.5 bg-ink border border-slate/40 rounded text-parchment font-mono text-xs focus:outline-none focus:border-gemma-purple focus:ring-1 focus:ring-gemma-purple disabled:opacity-50 cursor-pointer"
          >
            {objectives.length === 0 ? (
              <option value="">Loading objectives...</option>
            ) : (
              objectives.map((obj) => (
                <option key={obj.id} value={obj.id}>
                  {obj.name} ({obj.id})
                </option>
              ))
            )}
          </select>

          <button
            type="button"
            onClick={onLaunchAttack}
            disabled={isAttacking || !selectedObjectiveId}
            className="px-4 py-1.5 bg-ledger-red/15 border border-ledger-red/50 hover:bg-ledger-red/25 text-ledger-red font-sans font-semibold text-xs rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shrink-0 flex items-center gap-1.5"
          >
            {isAttacking ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-ledger-red/30 border-t-ledger-red rounded-full animate-spin" />
                <span>Attacking Fleet...</span>
              </>
            ) : (
              <>
                <span>▸</span>
                <span>Launch Attack</span>
              </>
            )}
          </button>
        </div>

        {/* Verdict Badge in Header / Controls row if result present */}
        {attackResult && (
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
            <span className="text-slate">verdict:</span>
            <span
              className={`px-2.5 py-0.5 rounded font-mono font-bold uppercase tracking-wider border ${
                isBlocked
                  ? "text-ledger-red bg-ledger-red/10 border-ledger-red/40"
                  : "text-ledger-green bg-ledger-green/10 border-ledger-green/40"
              }`}
            >
              {isBlocked ? "✕ BLOCKED" : "✓ PASSED"}
            </span>
          </div>
        )}
      </div>

      {/* Attack Result Details Banner */}
      {attackResult && (
        <div className="pt-2 border-t border-slate/20 space-y-2 text-xs">
          {attackResult.payload?.payload_text && (
            <div className="text-slate flex flex-col sm:flex-row gap-1">
              <span className="text-gemma-purple shrink-0">payload:</span>
              <span className="text-parchment italic font-mono truncate">
                &ldquo;{attackResult.payload.payload_text}&rdquo;
              </span>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate text-[11px]">
            <div>
              blocked by:{" "}
              <span className="text-parchment font-semibold font-mono">
                {attackResult.blocked_by || "(not blocked)"}
              </span>
            </div>
            <span>│</span>
            <div>
              model:{" "}
              <span className="text-gemma-purple font-mono">
                {attackResult.payload.model_used || "gemma-3-27b-it"}
              </span>
            </div>
            <span>│</span>
            <div>
              chain:{" "}
              <span className="text-parchment font-mono">
                {attackResult.chain_id ? `${attackResult.chain_id.slice(0, 8)}…` : "unknown"}
              </span>
            </div>
            <span>│</span>
            <div>
              spans: <span className="text-parchment font-mono">{attackResult.spans_count}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
