export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
}
export interface Result {
  conversation_id: string;
  terminal_state: string;
  escalation_reason: string | null;
  patient_id: string | null;
  appointment_id: string | null;
  reply: string;
  tool_calls: ToolCall[];
  metrics: { turns: number; tokens: number; latency_ms: number };
}
export interface Run extends Result {
  run_id: string;
  created_at: string;
  excerpt: string;
  resolved: boolean;
  fingerprint: string;
}
export interface Event {
  type: "caller" | "agent" | "tool";
  text?: string;
  turn?: number;
  name?: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
}
export interface Detail {
  run_id: string;
  result: Result;
  trace: Event[];
  created_at: string;
  resolved: boolean;
  model: { model: string | null; status: string };
  schedule_unchanged: boolean;
  safety_preflight: string;
  determinism: { runs: number; fingerprints: string[]; stable: boolean };
}
export interface Sample {
  id: string;
  description: string;
  today: string;
  turns: string[];
  expected: { terminal_state: string; escalation_reason: string | null };
}
export interface Summary {
  runs: Run[];
  counters: {
    total: number;
    completed: number;
    escalated: number;
    urgent: number;
    open: number;
  };
}
