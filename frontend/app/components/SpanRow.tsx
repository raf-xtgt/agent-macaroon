"use client";

import { useState } from "react";
import type { SpanData } from "../types";

interface SpanRowProps {
  span: SpanData;
  treePrefix: string;
  nodeSymbol: string;
  indexNumber: number;
  gcpProjectId?: string;
  chainId?: string;
}

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toTimeString().split(" ")[0] + "." + String(d.getMilliseconds()).padStart(3, "0");
  } catch {
    return isoString;
  }
}

export function SpanRow({
  span,
  treePrefix,
  nodeSymbol,
  indexNumber,
  gcpProjectId = "agent-macaroon",
  chainId = "unknown",
}: SpanRowProps) {
  const [expanded, setExpanded] = useState(false);

  const isIssue = span.action_requested === "issue_macaroon";
  const isScreen = span.action_requested.startsWith("screen:");
  const isDeny = span.decision === "deny";

  let stampLabel = "[ ✓ ALLOW ]";

  let stampColor = "text-ledger-green border-ledger-green/40 bg-ledger-green/10";

  if (isIssue) {
    stampLabel = "[ ⛨ SEALED ]";
    stampColor = "text-seal-amber border-seal-amber/40 bg-seal-amber/10";
  } else if (isScreen) {
    if (isDeny) {
      stampLabel = "[ ⚑ FLAG ]";
      stampColor = "text-ledger-red border-ledger-red/40 bg-ledger-red/10";
    } else {
      stampLabel = "[ ✓ ALLOW ]";
      stampColor = "text-ledger-green border-ledger-green/40 bg-ledger-green/10";
    }
  } else if (isDeny) {
    stampLabel = "[ ✕ DENY ]";
    stampColor = "text-ledger-red border-ledger-red/40 bg-ledger-red/10";
  }

  const timeFormatted = formatTime(span.timestamp);
  const traceUrl = `https://console.cloud.google.com/traces/explorer?project=${encodeURIComponent(
    gcpProjectId
  )}&query=chain_id%3D${encodeURIComponent(chainId)}`;

  // Circled index numbers for mobile collapse
  const circledNumbers = ["⓪", "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"];
  const indexBadge = indexNumber <= 10 ? circledNumbers[indexNumber] : `(${indexNumber})`;

  return (
    <div className="group border-b border-slate/15 last:border-b-0 py-2.5 transition-colors hover:bg-slate/5">
      {/* Desktop layout */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="hidden md:flex items-baseline justify-between gap-4 cursor-pointer select-none font-mono text-sm"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
        aria-expanded={expanded}
      >
        <div className="flex items-baseline gap-2 min-w-0 flex-1">
          <span className="text-slate select-none whitespace-pre">{treePrefix}</span>
          <span
            className={
              isDeny
                ? "text-ledger-red font-bold"
                : isIssue
                ? "text-seal-amber font-bold"
                : "text-parchment"
            }
          >
            {nodeSymbol}
          </span>
          <span className="font-semibold text-parchment truncate">{span.agent_id}</span>
          <span className="text-slate truncate">{span.action_requested}</span>
        </div>

        <div className="flex items-center gap-4 shrink-0">
          <span className="text-slate text-xs">{timeFormatted}</span>
          <span
            className={`px-2 py-0.5 rounded text-xs font-mono font-medium tracking-wide border ${stampColor}`}
          >
            {stampLabel}
          </span>
        </div>
      </div>

      {/* Inline reason / metadata for desktop */}
      <div className="hidden md:flex items-center justify-between text-xs font-mono text-slate pl-4 ml-6 mt-1">
        <div className="truncate flex-1 flex items-center gap-2">
          {span.defense_layer && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold border border-slate/30 bg-slate/10 text-shield-blue shrink-0">
              {span.defense_layer.replace(/^F\d+_/, "").replace(/_/g, " ").toUpperCase()}
            </span>
          )}
          {isScreen ? (
            isDeny ? (
              <span className="text-ledger-red truncate">quarantined: {span.reason}</span>
            ) : (
              <span className="text-slate">clean</span>
            )
          ) : (
            <span className={`truncate ${isDeny ? "text-ledger-red" : "text-slate"}`}>
              {span.reason ? `reason: ${span.reason}` : ""}
            </span>
          )}
        </div>
        <a
          href={traceUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="text-slate/70 hover:text-seal-amber text-xs ml-4 shrink-0 hover:underline"
        >
          view trace ↗
        </a>
      </div>

      {/* Mobile layout */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex md:hidden flex-col gap-1 cursor-pointer select-none font-mono text-sm py-1"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 truncate">
            <span className="text-seal-amber text-base">{indexBadge}</span>
            <span className="font-semibold text-parchment truncate">{span.agent_id}</span>
          </div>
          <span
            className={`px-1.5 py-0.5 rounded text-[11px] font-mono tracking-tight border shrink-0 ${stampColor}`}
          >
            {stampLabel}
          </span>
        </div>
        <div className="flex items-center justify-between text-xs text-slate">
          <span className="truncate">{span.action_requested}</span>
          <span className="text-[11px] shrink-0">{timeFormatted}</span>
        </div>
      </div>

      {/* Expanded detail card */}
      {expanded && (
        <div className="mt-3 p-3.5 bg-ink/90 border border-slate/30 rounded font-mono text-xs text-parchment space-y-2 animate-in fade-in duration-150">
          <div className="flex items-center justify-between border-b border-slate/20 pb-2">
            <span className="text-slate font-sans uppercase tracking-wider text-[10px]">
              Span Details: {span.span_id.slice(0, 8)}…
            </span>
            <span className="text-slate text-[11px]">{span.timestamp}</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[110px_1fr] gap-1.5">
            <span className="text-slate">decision:</span>
            <span
              className={`font-semibold ${
                isDeny ? "text-ledger-red" : isIssue ? "text-seal-amber" : "text-ledger-green"
              }`}
            >
              {span.decision.toUpperCase()}
            </span>

            <span className="text-slate">action:</span>
            <span>{span.action_requested}</span>

            <span className="text-slate">agent:</span>
            <span>{span.agent_id}</span>

            <span className="text-slate">reason:</span>
            <span className={isDeny ? "text-ledger-red" : "text-parchment"}>
              {span.reason || "(none)"}
            </span>

            {span.defense_layer && (
              <>
                <span className="text-slate">defense:</span>
                <span className="text-shield-blue font-semibold">
                  {span.defense_layer.replace(/^F\d+_/, "").replace(/_/g, " ").toUpperCase()}
                </span>
              </>
            )}

            {span.scope_snapshot && span.scope_snapshot.length > 0 && (
              <>
                <span className="text-slate">scope:</span>
                <span className="text-ledger-green">
                  {"{" + span.scope_snapshot.join(", ") + "}"}
                </span>
              </>
            )}

            {span.scope_snapshot && span.scope_snapshot.length === 0 && (
              <>
                <span className="text-slate">scope:</span>
                <span className="text-ledger-red">{"{ } (empty)"}</span>
              </>
            )}

            <span className="text-slate">parent_span:</span>
            <span className="text-slate/80">{span.parent_span_id || "(root span)"}</span>

            <span className="text-slate">macaroon:</span>
            <span className="text-slate/80">
              {span.macaroon_identifier_hash
                ? `id_hash=${span.macaroon_identifier_hash.slice(0, 12)}… (HMAC secret never logged)`
                : "(none)"}
            </span>
          </div>

          <div className="pt-2 border-t border-slate/20 flex justify-end">
            <a
              href={traceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-seal-amber hover:underline text-xs flex items-center gap-1"
            >
              [ view in Cloud Trace ↗ ]
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
