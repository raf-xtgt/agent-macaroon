"use client";

import { useState } from "react";
import type { AttackObjective, AttackResultData, AttackMode } from "../../types";

interface RedTeamPanelProps {
  objectives: AttackObjective[];
  selectedObjectiveId: string;
  onSelectObjective: (id: string) => void;
  attackMode: AttackMode;
  onSelectMode: (mode: AttackMode) => void;
  onLaunchAttack: () => void;
  isAttacking: boolean;
  attackResult: AttackResultData | null;
}

const MODE_LABELS: Record<AttackMode, { label: string; hint: string }> = {
  single: {
    label: "Single",
    hint: "One payload, one shot — tests a single injection against the fleet.",
  },
  campaign: {
    label: "Campaign",
    hint: "Multi-step adaptive attack — recon, strategy, evasion techniques, feedback loop.",
  },
};

export function RedTeamPanel({
  objectives,
  selectedObjectiveId,
  onSelectObjective,
  attackMode,
  onSelectMode,
  onLaunchAttack,
  isAttacking,
  attackResult,
}: RedTeamPanelProps) {
  const [payloadExpanded, setPayloadExpanded] = useState(false);
  const isBlocked = attackResult?.verdict === "blocked";

  return (
    <div className="border border-slate/30 rounded-lg bg-ink p-4 font-mono text-xs space-y-3 min-w-0">
      {/* Controls */}
      <div className="space-y-2.5">
        <div className="flex items-center gap-1.5 text-gemma-purple font-semibold font-sans uppercase tracking-wider text-xs">
          <span>⚔</span>
          <span>Red Team</span>
        </div>

        <select
          value={selectedObjectiveId}
          onChange={(e) => onSelectObjective(e.target.value)}
          disabled={isAttacking || objectives.length === 0}
          className="w-full px-3 py-1.5 bg-ink border border-slate/40 rounded text-parchment font-mono text-xs focus:outline-none focus:border-gemma-purple focus:ring-1 focus:ring-gemma-purple disabled:opacity-50 cursor-pointer"
        >
          {objectives.length === 0 ? (
            <option value="">Loading objectives...</option>
          ) : (
            objectives.map((obj) => (
              <option key={obj.id} value={obj.id}>
                {obj.name}
              </option>
            ))
          )}
        </select>

        <div className="flex flex-wrap items-center gap-2">
          {/* Mode selector */}
          <div className="flex items-center gap-1.5 shrink-0 group relative">
            <select
              value={attackMode}
              onChange={(e) => onSelectMode(e.target.value as AttackMode)}
              disabled={isAttacking}
              className="px-2.5 py-1.5 bg-ink border border-slate/40 rounded text-parchment font-mono text-xs focus:outline-none focus:border-gemma-purple focus:ring-1 focus:ring-gemma-purple disabled:opacity-50 cursor-pointer"
            >
              <option value="single">{MODE_LABELS.single.label}</option>
              <option value="campaign">{MODE_LABELS.campaign.label}</option>
            </select>
            <div className="hidden group-hover:block absolute bottom-full left-0 mb-1.5 w-64 p-2 bg-ink border border-slate/50 rounded shadow-lg text-[10px] text-slate font-sans z-10">
              <p className="text-parchment font-semibold mb-1">{MODE_LABELS[attackMode].label} mode</p>
              <p>{MODE_LABELS[attackMode].hint}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={onLaunchAttack}
            disabled={isAttacking || !selectedObjectiveId}
            className="px-4 py-1.5 bg-ledger-red/15 border border-ledger-red/50 hover:bg-ledger-red/25 text-ledger-red font-sans font-semibold text-xs rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shrink-0 flex items-center gap-1.5"
          >
            {isAttacking ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-ledger-red/30 border-t-ledger-red rounded-full animate-spin" />
                <span>Attacking...</span>
              </>
            ) : (
              <>
                <span>▸</span>
                <span>Launch Attack</span>
              </>
            )}
          </button>

          {/* Verdict Badge */}
          {attackResult && (
            <span
              className={`px-2.5 py-0.5 rounded font-mono font-bold uppercase tracking-wider border text-[10px] ${
                isBlocked
                  ? "text-ledger-red bg-ledger-red/10 border-ledger-red/40"
                  : "text-ledger-green bg-ledger-green/10 border-ledger-green/40"
              }`}
            >
              {isBlocked ? "✕ BLOCKED" : "✓ PASSED"}
            </span>
          )}
        </div>
      </div>

      {/* Attack Result Details */}
      {attackResult && (
        <div className="pt-2 border-t border-slate/20 space-y-2 text-xs min-w-0">
          {attackResult.payload?.payload_text && (
            <div className="text-slate min-w-0">
              <div className="flex items-start gap-1 min-w-0">
                <span className="text-gemma-purple shrink-0">payload:</span>
                <span
                  className={`text-parchment italic font-mono break-words min-w-0 ${payloadExpanded ? "whitespace-pre-wrap" : "line-clamp-2"}`}
                >
                  &ldquo;{attackResult.payload.payload_text}&rdquo;
                </span>
                <button
                  type="button"
                  onClick={() => setPayloadExpanded((p) => !p)}
                  className="shrink-0 px-1.5 py-0.5 text-[10px] text-slate hover:text-parchment bg-slate/10 hover:bg-slate/20 border border-slate/30 rounded transition-colors cursor-pointer"
                >
                  {payloadExpanded ? "less" : "more"}
                </button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-slate text-[10px]">
            <span>
              blocked by:{" "}
              <span className="text-parchment font-semibold font-mono">
                {attackResult.blocked_by || "none"}
              </span>
            </span>
            <span className="text-slate/30">│</span>
            <span>
              mode:{" "}
              <span className="text-gemma-purple font-mono">{attackMode}</span>
            </span>
            {attackResult.payload?.model_used && (
              <>
                <span className="text-slate/30">│</span>
                <span className="break-all">
                  model:{" "}
                  <span className="text-gemma-purple font-mono">
                    {attackResult.payload.model_used}
                  </span>
                </span>
              </>
            )}
            <span className="text-slate/30">│</span>
            <span>
              chain:{" "}
              <span className="text-parchment font-mono">
                {attackResult.chain_id ? `${attackResult.chain_id.slice(0, 8)}…` : "?"}
              </span>
            </span>
            <span className="text-slate/30">│</span>
            <span>
              spans: <span className="text-parchment font-mono">{attackResult.spans_count}</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
