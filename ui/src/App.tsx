import { useEffect, useState } from "react";
import { api, type BidDetail, type BidSummary, type ChecklistItem } from "./api";

const KIND_LABEL: Record<string, string> = {
  formal: "Formal (pre-flight)",
  suitability: "Suitability (Eignung)",
  award: "Award (Zuschlag)",
};

export function App() {
  const [bids, setBids] = useState<BidSummary[]>([]);
  const [selected, setSelected] = useState<BidDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listBids().then(setBids).catch((e) => setError(String(e)));
  }, []);

  async function open(id: string) {
    setError(null);
    try {
      setSelected(await api.getBid(id));
    } catch (e) {
      setError(String(e));
    }
  }

  async function toggle(item: ChecklistItem) {
    if (!selected) return;
    const next = item.status === "done" ? "open" : "done";
    await api.updateItem(selected.id, item.id, { status: next });
    await open(selected.id);
  }

  async function upload(item: ChecklistItem, file: File) {
    if (!selected) return;
    await api.uploadDocument(selected.id, file, item.requirement_type === "reference" ? "reference" : "supporting", item.id);
    await open(selected.id);
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>🤝 Bid Workspace</h1>
        <span className="sub">Collaborative bid preparation</span>
      </header>
      {error && <div className="error" data-testid="error">{error}</div>}
      <div className="layout">
        <aside className="sidebar">
          <h2>Bids</h2>
          <ul data-testid="bid-list">
            {bids.map((b) => (
              <li
                key={b.id}
                data-testid="bid-list-item"
                className={selected?.id === b.id ? "active" : ""}
                onClick={() => open(b.id)}
              >
                <div className="bid-title">{b.title}</div>
                <div className="bid-meta">
                  <span className={`pill status-${b.status}`}>{b.status}</span>
                  {b.customer && <span className="muted">{b.customer}</span>}
                </div>
              </li>
            ))}
          </ul>
        </aside>

        <main className="workspace">
          {!selected && <div className="empty">Select a bid to open its workspace.</div>}
          {selected && <Workspace bid={selected} onToggle={toggle} onUpload={upload} />}
        </main>
      </div>
    </div>
  );
}

function Workspace({
  bid,
  onToggle,
  onUpload,
}: {
  bid: BidDetail;
  onToggle: (i: ChecklistItem) => void;
  onUpload: (i: ChecklistItem, f: File) => void;
}) {
  const gate = bid.formal_gate;
  const byKind = (k: string) =>
    bid.checklist_items.filter((i) => i.criterion_kind === k).sort((a, b) => a.order - b.order);

  return (
    <div data-testid="workspace">
      <div className="ws-header">
        <h2>{bid.title}</h2>
        <div className="ws-sub">
          <span className="muted">{bid.customer}</span>
          <span className={`pill status-${bid.status}`}>{bid.status}</span>
          {bid.driver_user_id && <span className="pill">driver: {bid.driver_user_id}</span>}
          {bid.lots_in_scope && bid.lots_in_scope.length > 0 && (
            <span className="pill" data-testid="lots-badge">{bid.lots_in_scope.length} lots</span>
          )}
        </div>
      </div>

      {gate && (
        <div className={`gate ${gate.ready ? "gate-ok" : "gate-block"}`} data-testid="formal-gate">
          {gate.ready
            ? "✅ Formal pre-flight passed — all formal items resolved."
            : `⛔ Formal pre-flight blocked: ${gate.formal_open}/${gate.formal_total} formal items still open. Bids fail on formalities.`}
        </div>
      )}

      <div className="panels">
        <section className="checklist">
          {["formal", "suitability", "award"].map((k) => (
            <div key={k} className="kind-group">
              <h3>{KIND_LABEL[k]}</h3>
              {byKind(k).map((item) => (
                <div key={item.id} className="item" data-testid="checklist-item" data-kind={k}>
                  <label className="item-main">
                    <input
                      type="checkbox"
                      data-testid="item-checkbox"
                      checked={item.status === "done"}
                      onChange={() => onToggle(item)}
                    />
                    <span className={item.status === "done" ? "done" : ""}>{item.title}</span>
                  </label>
                  <div className="item-side">
                    {item.ai_verification && (
                      <span className={`verify verify-${item.ai_verification.status}`}>
                        {item.ai_verification.status}
                      </span>
                    )}
                    <label className="upload">
                      ⬆ upload
                      <input
                        type="file"
                        data-testid="item-upload"
                        style={{ display: "none" }}
                        onChange={(e) => e.target.files?.[0] && onUpload(item, e.target.files[0])}
                      />
                    </label>
                  </div>
                  {item.source_link && <div className="source">source: {item.source_link}</div>}
                </div>
              ))}
            </div>
          ))}
        </section>

        <aside className="side-panels">
          <div className="card">
            <h3>Deadlines</h3>
            <ul data-testid="deadlines">
              {bid.key_dates.length === 0 && <li className="muted">No key dates.</li>}
              {bid.key_dates.map((d) => (
                <li key={d.id}>
                  <b>{d.kind}</b>: {d.date ? new Date(d.date).toLocaleDateString() : "—"}
                  {typeof d.days_remaining === "number" && (
                    <span className={`days ${d.days_remaining < 7 ? "urgent" : ""}`}>{d.days_remaining}d</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
          <div className="card">
            <h3>Documents</h3>
            <ul data-testid="documents">
              {bid.documents.length === 0 && <li className="muted">No documents yet.</li>}
              {bid.documents.map((doc) => (
                <li key={doc.id}>
                  {doc.filename} <span className="pill small">{doc.kind}</span>
                  {doc.ai_verification && (
                    <span className={`verify verify-${doc.ai_verification.status}`}>{doc.ai_verification.status}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
