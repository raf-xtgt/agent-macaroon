/**
 * Type definitions for the F6 Replay UI.
 */

export interface SpanData {
  span_id: string;
  parent_span_id: string | null;
  agent_id: string;
  action_requested: string;
  decision: "allow" | "deny";
  reason: string;
  timestamp: string;
  macaroon_identifier_hash: string | null;
  chain_id?: string | null;
  human_subject_id?: string | null;
  purpose?: string | null;
  defense_layer?: string | null;
  scope_snapshot?: string[] | null;
}

export interface ReplayResponse {
  chain_id: string;
  human_subject_id: string | null;
  purpose: string | null;
  started_at: string;
  hop_count: number;
  verdict: "allowed" | "blocked";
  spans: SpanData[];
}

export interface AttackObjective {
  id: string;
  name: string;
  description: string;
  injection_surface: string;
  target_tools: string[];
}

export interface BlastRadiusData {
  score: number;
  reachable_agents: string[];
  reachable_agent_count: number;
  exposed_tools: string[];
  exposed_tool_count: number;
  sensitivity_breakdown: Record<string, number>;
  max_sensitivity: string;
}

export interface AttackResultData {
  objective: {
    id: string;
    name: string;
    description: string;
    injection_surface: string;
  };
  payload: {
    payload_text: string;
    model_used: string;
    injection_surface: string;
    target_tool: string | null;
  };
  verdict: string;
  blocked_by: string | null;
  chain_id: string | null;
  spans_count: number;
  denial_reasons: string[];
  blast_radius: BlastRadiusData | null;
}

export interface ArmorStatus {
  active_pattern_count: number;
  runtime_patterns: string[];
  model_armor: {
    enabled: boolean;
    template: string | null;
  };
}

export type AttackMode = "single" | "campaign";

// ---------------------------------------------------------------------------
// Narrative span helpers
// ---------------------------------------------------------------------------

/** Phase labels for red-team narrative spans. */
export type NarrativePhase =
  | "RECON"
  | "PLAN"
  | "GENERATE"
  | "STEP"
  | "ADAPT"
  | "COMPLETE"
  | "INJECT"
  | "RESULT";

/** Map from action_requested values to narrative phase labels. */
const ACTION_TO_PHASE: Record<string, NarrativePhase> = {
  fleet_recon: "RECON",
  plan_campaign: "PLAN",
  generate_payload: "GENERATE",
  execute_step: "STEP",
  adapt_step: "ADAPT",
  campaign_complete: "COMPLETE",
  inject_surface: "INJECT",
  attack_complete: "RESULT",
};

/** Returns true if the span was emitted by the red-team narrative system. */
export function isNarrativeSpan(span: SpanData): boolean {
  return span.agent_id.startsWith("red_team:");
}

/** Parse the narrative phase from a red-team span's action_requested field. */
export function parseNarrativePhase(span: SpanData): NarrativePhase {
  return ACTION_TO_PHASE[span.action_requested] ?? "RESULT";
}

/** Format a timestamp as HH:MM:SS.mmm for narrative timeline display. */
export function formatNarrativeTimestamp(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    const ms = String(d.getMilliseconds()).padStart(3, "0");
    return `${hh}:${mm}:${ss}.${ms}`;
  } catch {
    return isoString;
  }
}

