// Thin API client for the bidding backend. Behind nginx the app is served at
// /ms/bidding/, and the API lives at /ms/bidding/api/v1 — so a relative base works
// both in the ecosystem and via the Vite dev proxy.
const BASE = `${import.meta.env.BASE_URL.replace(/\/$/, "")}/api/v1`.replace("/./", "/");

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.status === 204 ? (undefined as T) : res.json();
}

export interface BidSummary {
  id: string;
  source_ref: string;
  title: string;
  customer?: string;
  status: string;
  driver_user_id?: string;
  portal_key?: string;
  version: number;
}

export interface ChecklistItem {
  id: string;
  criterion_kind: "formal" | "suitability" | "award";
  requirement_type: string;
  title: string;
  source_link?: string;
  status: "open" | "done" | "n_a";
  ai_verification?: { status: string; detail: string } | null;
  assignee_user_id?: string;
  lot_scope?: string;
  order: number;
}

export interface KeyDate {
  id: string;
  kind: string;
  date?: string;
  source_link?: string;
  days_remaining?: number;
}

export interface DocumentOut {
  id: string;
  kind: string;
  sensitivity: string;
  filename: string;
  doc_type?: string;
  uploaded_by?: string;
  ai_verification?: { status: string; detail: string } | null;
  checklist_item_id?: string;
  created_at: string;
}

export interface FormalGate {
  formal_total: number;
  formal_open: number;
  ready: boolean;
  blocking: { id: string; title: string }[];
}

export interface BidDetail extends BidSummary {
  source_kind: string;
  lots_in_scope?: (string | number)[];
  cluster?: string;
  loss_reason?: string;
  collaborators: { id: string; user_id: string; role: string }[];
  checklist_items: ChecklistItem[];
  documents: DocumentOut[];
  key_dates: KeyDate[];
  formal_gate?: FormalGate;
}

export interface ScoreCriterion {
  key: string;
  label: string;
  weight: number;
  score: number;
  detail: string;
}

export interface Score {
  total: number;
  criteria: ScoreCriterion[];
}

export interface EvidenceMatch {
  checklist_item_id: string;
  requirement: string;
  document_id: string;
  filename: string;
  from_corpus: boolean;
  overlap: number;
  source: string;
}

export interface MatrixSummary {
  matrix_name: string;
  total_points: number;
  threshold: number;
  max_points: number;
  verdict: "bid" | "no_bid";
  overrides: number;
}

export interface Recommendation {
  recommendation: "bid" | "no_bid" | "review";
  confidence: number;
  score: Score;
  matrix: MatrixSummary | null;
  reusable_evidence: EvidenceMatch[];
  reasons: string[];
}

export interface MatrixCategoryRow {
  category_id: string;
  headline: string;
  explanation?: string | null;
  weight: number;
  ai_score: number | null;
  ai_rationale: string | null;
  human_score: number | null;
  human_note: string | null;
  overridden_by: string | null;
  effective_score: number | null;
  weighted_points: number | null;
}

export interface MatrixEvaluation {
  matrix_id: string;
  matrix_name: string;
  matrix_version: number;
  threshold: number;
  max_points: number;
  total_points: number | null;
  verdict: "bid" | "no_bid" | null;
  evaluated: boolean;
  categories: MatrixCategoryRow[];
}

export interface MatrixCategory {
  id: string;
  headline: string;
  explanation?: string | null;
  weight: number;
}

export interface Matrix {
  id: string;
  name: string;
  threshold: number;
  version: number;
  max_points: number;
  source_filename?: string | null;
  uploaded_by?: string | null;
  categories: MatrixCategory[];
}

export interface ServiceStats {
  bids_total: number;
  bids_by_status: Record<string, number>;
  requirements_detected: number;
  checklist_items_total: number;
  checklist_items_open: number;
  key_dates_total: number;
  deadlines_due_14d: number;
  corpus_documents: number;
  matrix_evaluated_bids: number;
  human_overrides: number;
  activity_events: number;
  matrix: { name: string; version: number; threshold: number } | null;
  prompt_versions: Record<string, number>;
}

export interface PromptConfig {
  category: string;
  prompt_template: string;
  version: number;
  updated_at: string | null;
  is_default: boolean;
}

export interface MatrixHistoryEntry {
  version: number;
  change_summary?: string | null;
  created_by?: string | null;
  created_at: string;
  data: Record<string, unknown>;
}

export interface LibraryUsage {
  bid_id: string;
  bid_title: string;
  bid_status: string;
  won: boolean;
  customer?: string;
  cpv_codes: string[];
}

export interface LibraryResult {
  fingerprint: string;
  document_id: string;
  filename: string;
  kind: string;
  sensitivity: string;
  doc_type?: string;
  snippet: string;
  score: number;
  proven: boolean;
  usages: LibraryUsage[];
}

export interface LibrarySearch {
  results: LibraryResult[];
  total: number;
  visible_sensitivities: string[];
}

export const api = {
  listBids: () => req<BidSummary[]>("/bids"),
  getBid: (id: string) => req<BidDetail>(`/bids/${id}`),
  getRecommendation: (id: string) => req<Recommendation>(`/bids/${id}/recommendation`),
  searchLibrary: (params: { q?: string; kind?: string; client?: string; cpv?: string }) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v)) as Record<string, string>,
    );
    return req<LibrarySearch>(`/library/search?${qs.toString()}`);
  },
  matchDocuments: (id: string) =>
    req<{ matches: EvidenceMatch[]; corpus_size: number }>(`/bids/${id}/match`, { method: "POST" }),
  getStats: () => req<ServiceStats>("/stats"),
  getConfigs: () => req<Record<string, PromptConfig>>("/config"),
  updateConfig: (category: string, body: { prompt_template: string; change_summary?: string }) =>
    req<PromptConfig>(`/config/${category}`, { method: "POST", body: JSON.stringify(body) }),
  getMatrix: () => req<Matrix>("/matrix"),
  updateMatrix: (body: { name?: string; threshold?: number; change_summary?: string }) =>
    req<Matrix>("/matrix", { method: "PUT", body: JSON.stringify(body) }),
  addMatrixCategory: (body: { headline: string; explanation?: string; weight: number }) =>
    req<Matrix>("/matrix/categories", { method: "POST", body: JSON.stringify(body) }),
  updateMatrixCategory: (id: string, body: { headline?: string; explanation?: string; weight?: number }) =>
    req<Matrix>(`/matrix/categories/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteMatrixCategory: (id: string) => req<Matrix>(`/matrix/categories/${id}`, { method: "DELETE" }),
  getMatrixHistory: () => req<MatrixHistoryEntry[]>("/matrix/history"),
  getMatrixEvaluation: (bidId: string) => req<MatrixEvaluation>(`/bids/${bidId}/matrix-evaluation`),
  runMatrixEvaluation: (bidId: string) =>
    req<MatrixEvaluation>(`/bids/${bidId}/matrix-evaluation`, { method: "POST" }),
  overrideMatrixCategory: (bidId: string, categoryId: string, body: { score: number | null; note?: string }) =>
    req<MatrixEvaluation>(`/bids/${bidId}/matrix-evaluation/${categoryId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  uploadMatrix: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/matrix`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json();
  },
  acceptMatch: (bidId: string, body: { checklist_item_id: string; document_id: string }) =>
    req<{ checklist_item_id: string; ai_verification: Record<string, unknown> }>(`/bids/${bidId}/match/accept`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  rejectMatch: (bidId: string, body: { checklist_item_id: string; document_id: string; reason?: string }) =>
    req<{ checklist_item_id: string; rejected_document_id: string }>(`/bids/${bidId}/match/reject`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateItem: (bidId: string, itemId: string, body: { status?: string; assignee_user_id?: string }) =>
    req<ChecklistItem>(`/bids/${bidId}/checklist/${itemId}`, { method: "PATCH", body: JSON.stringify(body) }),
  setStatus: (bidId: string, body: { status: string; expected_version: number; loss_reason?: string }) =>
    req<BidDetail>(`/bids/${bidId}/status`, { method: "POST", body: JSON.stringify(body) }),
  portalGuide: (bidId: string) => req<any>(`/bids/${bidId}/portal-guide`),
  uploadDocument: async (bidId: string, file: File, kind: string, checklistItemId?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    if (checklistItemId) fd.append("checklist_item_id", checklistItemId);
    const res = await fetch(`${BASE}/bids/${bidId}/documents`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json() as Promise<DocumentOut>;
  },
};
