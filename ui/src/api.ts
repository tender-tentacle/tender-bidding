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

export const api = {
  listBids: () => req<BidSummary[]>("/bids"),
  getBid: (id: string) => req<BidDetail>(`/bids/${id}`),
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
