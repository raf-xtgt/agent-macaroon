import type { SpanData } from "../types";
import { SpanRow } from "./SpanRow";

interface TimelineTreeProps {
  spans: SpanData[];
  gcpProjectId?: string;
  chainId?: string;
}

interface FlattenedTreeNode {
  span: SpanData;
  treePrefix: string;
  nodeSymbol: string;
  indexNumber: number;
}

export function TimelineTree({ spans, gcpProjectId, chainId }: TimelineTreeProps) {
  if (!spans || spans.length === 0) {
    return null;
  }

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

  const flattened: FlattenedTreeNode[] = [];
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

    flattened.push({
      span: node,
      treePrefix: linePrefix,
      nodeSymbol: symbol,
      indexNumber: globalIndex++,
    });

    const children = childrenMap.get(node.span_id) || [];
    const nextChildPrefix = depth === 0 ? "│  " : currentPrefix + (isLastChild ? "   " : "│  ");

    for (let i = 0; i < children.length; i++) {
      const child = children[i];
      const isLast = i === children.length - 1;
      traverse(child, depth + 1, nextChildPrefix, isLast);
    }
  }

  // Find root spans (parent_span_id is null or not in spanIdSet)
  const rootSpans = spans.filter(
    (s) => s.parent_span_id === null || !spanIdSet.has(s.parent_span_id)
  );

  for (let i = 0; i < rootSpans.length; i++) {
    traverse(rootSpans[i], 0, "", i === rootSpans.length - 1);
  }

  // If any span wasn't reached (cyclic or broken hierarchy), append gracefully
  for (const span of spans) {
    if (!visited.has(span.span_id)) {
      traverse(span, 0, "", true);
    }
  }

  return (
    <div className="space-y-1">
      {flattened.map((item) => (
        <SpanRow
          key={item.span.span_id}
          span={item.span}
          treePrefix={item.treePrefix}
          nodeSymbol={item.nodeSymbol}
          indexNumber={item.indexNumber}
          gcpProjectId={gcpProjectId}
          chainId={chainId}
        />
      ))}
    </div>
  );
}
