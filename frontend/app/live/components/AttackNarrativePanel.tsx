"use client";

import { useState } from "react";
import type { SpanData, NarrativePhase } from "../../types";
import {
  isNarrativeSpan,
  parseNarrativePhase,
  formatNarrativeTimestamp,
} from "../../types";

interface AttackNarrativePanelProps {
  spans: SpanData[];
}

/** Phase display config: prefix symbol, accent color. */
const PHASE_CONFIG: Record<
  NarrativePhase,
  { symbol: string; accent: string; label: string }
> = {
  RECON: { symbol: "\u25CF", accent: "text-gemma-purple", label: "RECON" },
  PLAN: { symbol: "\u25CF", accent: "text-gemma-purple", label: "PLAN" },
  GENERATE: { symbol: "\u25CF", accent: "text-gemma-purple", label: "GENERATE" },
  INJECT: { symbol: "\u25CF", accent: "text-gemma-purple", label: "INJECT" },
  STEP: { symbol: "", accent: "", label: "STEP" }, // rendered as a card
  ADAPT: { symbol: "\u25D0", accent: "text-gemma-purple", label: "ADAPT" },
  COMPLETE: { symbol: "\u25A0", accent: "", label: "COMPLETE" },
  RESULT: { symbol: "\u25A0", accent: "", label: "RESULT" },
};

/** Extract step number from reason text like "Step 2. surface=..." */
function extractStepNumber(reason: string): string {
  const match = reason.match(/^Step (\d+)/);
  return match ? match[1] : "?";
}

/** Extract key=value pairs from reason text for STEP spans. */
function extractStepFields(reason: string): Record<string, string> {
  const fields: Record<string, string> = {};
  const pairs = reason.split(". ");
  for (const pair of pairs) {
    const eqMatch = pair.match(/^(\w+)=(.+)$/);
    if (eqMatch) {
      fields[eqMatch[1]] = eqMatch[2];
    }
  }
  return fields;
}

function StepCard({ span }: { span: SpanData }) {
  const stepNum = extractStepNumber(span.reason);
  const fields = extractStepFields(span.reason);
  const isBlocked = span.decision === "deny";
  const verdictText = isBlocked ? "\u2715 BLOCKED" : "\u2713 PASSED";
  const verdictColor = isBlocked
    ? "text-ledger-red border-ledger-red/40"
    : "text-ledger-green border-ledger-green/40";

  return (
    <div className="border border-slate/30 rounded-md bg-ink/50 p-3 space-y-1.5 text-[11px]">
      <div className="flex items-center justify-between">
        <span className="text-parchment font-semibold font-sans text-xs">
          STEP {stepNum}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate font-mono">
            {formatNarrativeTimestamp(span.timestamp)}
          </span>
          <span
            className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] uppercase tracking-wider border ${verdictColor}`}
          >
            {verdictText}
          </span>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-slate font-mono">
        {fields.surface && (
          <span>
            surface: <span className="text-parchment">{fields.surface}</span>
          </span>
        )}
        {fields.technique && (
          <span>
            technique:{" "}
            <span className="text-parchment">{fields.technique}</span>
          </span>
        )}
        {fields.target_tool && (
          <span>
            target: <span className="text-parchment">{fields.target_tool}</span>
            {fields.target_agent && (
              <>
                {" "}
                <span className="text-slate">&rarr;</span>{" "}
                <span className="text-parchment">{fields.target_agent}</span>
              </>
            )}
          </span>
        )}
      </div>
      {fields.defense && (
        <div className="text-slate font-mono">
          defense:{" "}
          <span className="text-shield-blue font-semibold">{fields.defense}</span>
          {fields.reasons && (
            <span className="text-slate/80 italic">
              {" "}
              &mdash; {fields.reasons.replace(/^\[/, "").replace(/]$/, "")}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function InlineSpan({ span, phase }: { span: SpanData; phase: NarrativePhase }) {
  const config = PHASE_CONFIG[phase];

  // COMPLETE and RESULT use verdict coloring
  const isTerminal = phase === "COMPLETE" || phase === "RESULT";
  const isBlocked = span.decision === "deny";
  const terminalColor = isBlocked ? "text-ledger-red" : "text-ledger-green";
  const accentColor = isTerminal ? terminalColor : config.accent;

  return (
    <div className="flex items-start gap-2 py-1.5 text-[11px]">
      <span className={`shrink-0 ${accentColor} text-sm leading-none pt-0.5`}>
        {config.symbol}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className={`font-sans font-semibold text-xs uppercase tracking-wider ${accentColor}`}>
            {config.label}
          </span>
          <span className="text-[10px] text-slate font-mono shrink-0">
            {formatNarrativeTimestamp(span.timestamp)}
          </span>
        </div>
        <p className="text-parchment/90 font-mono text-[11px] mt-0.5 break-words">
          {span.reason}
        </p>
      </div>
    </div>
  );
}

export function AttackNarrativePanel({ spans }: AttackNarrativePanelProps) {
  const [collapsed, setCollapsed] = useState(false);

  const narrativeSpans = spans.filter(isNarrativeSpan);
  if (narrativeSpans.length === 0) return null;

  return (
    <div className="border border-slate/30 rounded-lg bg-ink p-4 font-mono text-xs space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate/20 pb-2">
        <div className="flex items-center gap-1.5 text-gemma-purple font-semibold font-sans uppercase tracking-wider text-xs">
          <span>&#x2694;</span>
          <span>Attack Narrative</span>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-expanded={!collapsed}
          className="px-2 py-0.5 text-[10px] text-slate hover:text-parchment bg-slate/10 hover:bg-slate/20 border border-slate/30 rounded transition-colors cursor-pointer"
        >
          {collapsed ? "\u25B8 expand" : "\u25BE collapse"}
        </button>
      </div>

      {/* Timeline */}
      {!collapsed && (
        <div className="space-y-2" role="region" aria-label="Attack narrative timeline">
          {narrativeSpans.map((span) => {
            const phase = parseNarrativePhase(span);
            if (phase === "STEP") {
              return <StepCard key={span.span_id} span={span} />;
            }
            return (
              <InlineSpan key={span.span_id} span={span} phase={phase} />
            );
          })}
        </div>
      )}
    </div>
  );
}
