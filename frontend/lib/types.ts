// Wire types matching the frozen backend contract exactly. Do not add,
// rename, or reinterpret fields — see the architect's spec.

/** A flat object of proposal fields. Keys vary by proposal; never assumed. */
export type ProposalObject = Record<string, string | number | boolean | null>;

export interface ChatRequest {
  thread_id: string;
  message: string;
}

export interface ChatMessageResponse {
  type: "message";
  text: string;
}

export interface ChatApprovalResponse {
  type: "approval_request";
  text: string;
  proposal: ProposalObject;
}

export type ChatResponse = ChatMessageResponse | ChatApprovalResponse;

/** One rendered item in the conversation transcript (UI-only concept). */
export type ChatTurn =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; text: string; proposal?: ProposalObject }
  | { id: string; role: "error"; text: string; retryText: string };
