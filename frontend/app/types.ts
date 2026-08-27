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

