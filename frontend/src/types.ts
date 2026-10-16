export type User = { id: number; email: string; role: string; is_active: boolean; created_at: string }
export type Message = { id: number; ticket_id: number; sender_type: string; content: string; created_at: string }
export type Ticket = {
  id: number; user_id: number; title: string; category: string; priority: string;
  intent: string | null; route_to: string | null; status: string; created_at: string;
  updated_at: string; messages?: Message[]; classification_source: string | null;
  classification_attempts: number | null; classification_latency_ms: number | null;
  classification_fallback_used: boolean;
}
export type AgentRun = {
  id: number; ticket_id: number; action: string | null; action_reason: string | null;
  tool_name: string | null; tool_args: Record<string, unknown> | null;
  tool_result: Record<string, unknown> | null; final_reply: string | null;
  review_approved: boolean | null; review_issues: string[] | null;
  checkpoint_status: string | null; rag_trace: Record<string, any> | null;
  memory_trace: Record<string, any> | null; context_trace: Record<string, any> | null;
  total_latency_ms: number | null; created_at: string;
}
export type KnowledgeDocument = { id: number; title: string; source: string; is_active: boolean; created_at: string; updated_at: string }
export type RetrievedKnowledge = { chunk_id: number; title: string; source: string; content: string; score: number; keyword_score?: number; vector_score?: number; retrieval_method?: string }
