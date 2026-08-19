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
