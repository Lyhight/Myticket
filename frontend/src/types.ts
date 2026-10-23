export type User = { id: number; email: string; role: string; is_active: boolean; created_at: string }
export type Message = { id: number; ticket_id: number; sender_type: string; content: string; created_at: string }
export type Ticket = {
  id: number; user_id: number; title: string; category: string; priority: string;
  intent: string | null; route_to: string | null; status: string; created_at: string;
  updated_at: string; messages?: Message[]; classification_source: string | null;
  classification_attempts: number | null; classification_latency_ms: number | null;
  classification_fallback_used: boolean;
  assigned_agent_id: number | null; escalation_reason: string | null;
  claimed_at: string | null; human_started_at: string | null; resolved_at: string | null;
}
export type DomainEvent = {
  id: number; type: string; aggregate_type: string; aggregate_id: number;
  payload: Record<string, any>; created_at: string;
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
export type FeedbackRating = 'UP' | 'DOWN'
export type MessageFeedback = {
  id: number; ticket_id: number; message_id: number; agent_run_id: number | null;
  user_id: number; rating: FeedbackRating; comment: string | null;
  created_at: string; updated_at: string;
}
export type KnowledgeGap = {
  id: number; ticket_id: number | null; agent_run_id: number | null;
  feedback_id: number | null; question: string; suggested_answer: string | null;
  source: string; reason: string; status: 'PENDING' | 'APPROVED' | 'REJECTED';
  occurrence_count: number; reviewer_note: string | null; reviewed_by: number | null;
  reviewed_at: string | null; knowledge_document_id: number | null;
  created_at: string; updated_at: string;
}
