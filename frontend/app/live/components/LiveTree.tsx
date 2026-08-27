"use client";

import type { SpanData } from "../../types";
import { SpanRow } from "../../components/SpanRow";
import { ScopeBar } from "./ScopeBar";

interface LiveTreeProps {
  spans: SpanData[];
  gcpProjectId?: string;
  chainId?: string;
  isAttacking?: boolean;
  activeObjectiveName?: string | null;
}

interface FlattenedLiveNode {
  span: SpanData;
  treePrefix: string;
  nodeSymbol: string;
  indexNumber: number;
  depth: number;
  isHop: boolean;
  verbCount: number;
  scopeLinePrefix: string;
  isParallelLeader?: boolean;
  parallelCount?: number;
}

function deriveVerbCount(span: SpanData, depth: number): number {
  const reason = (span.reason || "").toLowerCase();

  // Check explicit reason patterns
  if (reason.includes("allowed=")) {
    const match = reason.match(/allowed=([a-z_, ]+)/);
    if (match && match[1]) {
      return match[1].split(",").map((s) => s.trim()).filter(Boolean).length;
    }
  }
  if (reason.includes("scope narrowed to")) {
    const match = reason.match(/scope narrowed to ([a-z_, ]+)/);
    if (match && match[1]) {
      return match[1].split(",").map((s) => s.trim()).filter(Boolean).length;
    }
  }
  if (reason.includes("4 verbs") || reason.includes("root macaroon")) {
    return 4;
  }
  if (reason.includes("3 verbs")) return 3;
  if (reason.includes("2 verbs")) return 2;
  if (reason.includes("1 verb")) return 1;

  // Depth-based attenuation heuristic (scope only narrows)
  if (depth === 0) return 4;
  if (depth === 1) return 3;
  if (depth === 2) return 2;
  return 1;
}

export function LiveTree({
  spans,
  gcpProjectId = "agent-macaroon",
  chainId = "live-session",
  isAttacking = false,
  activeObjectiveName,
}: LiveTreeProps) {
  if (!spans || spans.length === 0) {
    return (
      <div className="py-16 text-center space-y-3 font-mono text-slate">
        <span className="text-3xl text-seal-amber inline-block">⛨</span>
        <p className="text-parchment text-sm">Waiting for live delegation events...</p>
        <p className="text-xs text-slate">Launch an attack or invoke an agent query to begin streaming.</p>
      </div>
    );
  }

  // Find root span details
  const rootSpan = spans.find((s) => s.parent_span_id === null) || spans[0];
  const effectiveChainId = rootSpan?.chain_id || chainId;
  const human = rootSpan?.human_subject_id || "anonymous";
  const purpose = rootSpan?.purpose || "compliance check on Google UK";
  const lastSpanId = spans[spans.length - 1]?.span_id;

  // Map children by parent_span_id
  const childrenMap = new Map<string | null, SpanData[]>();
  const spanIdSet = new Set<string>();

  for (const span of spans) {
    spanIdSet.add(span.span_id);
    const parentId = span.parent_span_id;
    const list = childrenMap.get(parentId) || [];
    list.push(span);
    childrenMap.set(parentId, list);
  }

  const flattened: FlattenedLiveNode[] = [];
  let globalIndex = 1;
  const visited = new Set<string>();

  function traverse(node: SpanData, depth: number, currentPrefix: string, isLastChild: boolean) {
    if (visited.has(node.span_id)) return;
    visited.add(node.span_id);

    const isIssueOrTransfer =
      node.action_requested === "issue_macaroon" ||
      node.action_requested === "transfer_to_agent";

    let symbol = isIssueOrTransfer ? "●" : "○";
    if (node.decision === "deny") {
      symbol = "✕";
    }

    let linePrefix = "";
    if (depth > 0) {
      linePrefix = currentPrefix + (isLastChild ? "└─" : "├─");
    }

    const verbCount = deriveVerbCount(node, depth);
    const scopeLinePrefix = depth === 0 ? "│  " : currentPrefix + (isLastChild ? "   │  " : "│  │  ");

    // Detect if this node has multiple parallel children
    const children = childrenMap.get(node.span_id) || [];
    const isParallelLeader =
      node.agent_id.includes("data_retrieval") && children.length >= 3;

    flattened.push({
      span: node,
      treePrefix: linePrefix,
      nodeSymbol: symbol,
      indexNumber: globalIndex++,
      depth,
      isHop: isIssueOrTransfer,
      verbCount,
      scopeLinePrefix,
      isParallelLeader,
      parallelCount: children.length,
    });

    const nextChildPrefix = depth === 0 ? "│  " : currentPrefix + (isLastChild ? "   " : "│  ");

    for (let i = 0; i < children.length; i++) {
      const child = children[i];
      const isLast = i === children.length - 1;
      traverse(child, depth + 1, nextChildPrefix, isLast);
    }
  }

  // Find root spans
  const rootSpans = spans.filter(
    (s) => s.parent_span_id === null || !spanIdSet.has(s.parent_span_id)
  );

  for (let i = 0; i < rootSpans.length; i++) {
    traverse(rootSpans[i], 0, "", i === rootSpans.length - 1);
  }

  // Fallback for detached or cyclic spans
  for (const span of spans) {
    if (!visited.has(span.span_id)) {
      traverse(span, 0, "", true);
    }
  }

  return (
    <div className="space-y-3 font-mono">
      {/* Session Provenance Header */}
      <div className="p-3 bg-ink/70 border border-slate/25 rounded-md text-xs space-y-1">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <div>
            <span className="text-slate">chain: </span>
            <span className="text-parchment font-semibold">
              {effectiveChainId ? `${effectiveChainId.slice(0, 8)}…` : "(none)"}
            </span>
          </div>
          <div>
            <span className="text-slate">human: </span>
            <span className="text-parchment">{human}</span>
          </div>
          {activeObjectiveName && (
            <div className="px-2 py-0.5 rounded bg-gemma-purple/10 border border-gemma-purple/40 text-gemma-purple text-[11px] font-semibold flex items-center gap-1">
              <span>⚠ RED TEAM:</span>
              <span>{activeObjectiveName}</span>
            </div>
          )}
        </div>
        <div>
          <span className="text-slate">purpose: </span>
          <span className="text-parchment italic">&ldquo;{purpose}&rdquo;</span>
        </div>
      </div>

      {/* Delegation Tree Rows */}
      <div className="space-y-1 pt-1">
        {flattened.map((item) => {
          const isLatest = item.span.span_id === lastSpanId;
          const isDeny = item.span.decision === "deny";

          return (
            <div
              key={item.span.span_id}
              className={`rounded transition-all duration-300 ${
                isLatest
                  ? isDeny
                    ? "bg-ledger-red/15 ring-1 ring-ledger-red/50"
                    : "bg-slate/10 ring-1 ring-seal-amber/40"
                  : ""
              }`}
            >
              <SpanRow
                span={item.span}
                treePrefix={item.treePrefix}
                nodeSymbol={item.nodeSymbol}
                indexNumber={item.indexNumber}
                gcpProjectId={gcpProjectId}
                chainId={effectiveChainId || undefined}
              />

              {/* Scope Attenuation Bar attached to delegation hops */}
              {item.isHop && (
                <div className="pl-4 ml-6 py-0.5 flex items-center">
                  <span className="text-slate/40 select-none whitespace-pre text-xs">
                    {item.scopeLinePrefix}
                  </span>
                  <ScopeBar currentVerbs={item.verbCount} maxVerbs={4} />
                </div>
              )}

              {/* Parallel Agent Group Box Header if detected */}
              {item.isParallelLeader && (
                <div className="ml-12 my-1 px-2.5 py-1 bg-slate/10 border border-slate/30 rounded text-[11px] text-seal-amber font-mono flex items-center gap-2">
                  <span>⚡ PARALLEL ({item.parallelCount} agents dispatched concurrently)</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Streaming Activity Indicator */}
      {isAttacking && (
        <div className="flex items-center gap-2 pt-2 text-xs text-seal-amber font-mono animate-pulse">
          <span className="inline-block w-2 h-2 rounded-full bg-seal-amber animate-ping" />
          <span>▼ (streaming delegation events…)</span>
        </div>
      )}
    </div>
  );
}
