import { useCallback, useEffect, useState } from "react";
import {
  PButton,
  PHeading,
  PIcon,
  PInlineNotification,
  PTag,
  PText,
} from "@porsche-design-system/components-react";
import {
  api,
  type BidDetail,
  type BidSummary,
  type ChecklistItem,
  type KeyDate,
  type LibrarySearch,
  type Recommendation,
} from "./api";

const KIND_LABEL: Record<string, string> = {
  formal: "Formal (Pre-Flight)",
  suitability: "Suitability (Eignung)",
  award: "Award (Zuschlag)",
};

// Cross-service nav — mirrors the dashboard's AdminHeader so the suite reads as one app.
const SERVICES = [
  { name: "Crawling", path: "/ms/crawling/" },
  { name: "Enriching", path: "/ms/enriching/" },
  { name: "AI Service", path: "/ms/ai/" },
  { name: "IAM", path: "/ms/iam/admin" },
  { name: "Distributing", path: "/ms/distributing/" },
  { name: "Bidding", path: "/ms/bidding/", active: true },
];

type TagVariant = "primary" | "secondary" | "info" | "warning" | "success" | "error";

// Bid status → PDS tag variant (semantic colours, PDS v4.3.0).
const STATUS_VARIANT: Record<string, TagVariant> = {
  exploring: "info",
  draft: "secondary",
  in_progress: "warning",
  submitted: "info",
  won: "success",
  lost: "error",
  withdrawn: "secondary",
};

const RECO_STATE: Record<Recommendation["recommendation"], "success" | "warning" | "error"> = {
  bid: "success",
  review: "warning",
  no_bid: "error",
};

const RECO_HEADLINE: Record<Recommendation["recommendation"], string> = {
  bid: "Recommendation: BID",
  review: "Recommendation: REVIEW",
  no_bid: "Recommendation: NO BID",
};

function TenderTentacleLogo() {
  return (
    <svg viewBox="0 0 32 32" width={32} height={32} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#d5001c" />
      <path d="M8 16L14 10L20 16L14 22Z" fill="#fff" />
      <path d="M16 13L22 7L28 13L22 19Z" fill="rgba(255,255,255,0.5)" />
    </svg>
  );
}

function Header() {
  const host = typeof window !== "undefined" ? window.location.hostname : "";
  const isLocal = host.includes("localhost") || host.includes("127.0.0.1");
  const isTest = host.includes("-test");
  const envName = isLocal ? "LOCAL" : isTest ? "TEST" : "PROD";
  const envColor = isLocal ? "#8b8b9e" : isTest ? "#f59e0b" : "#d5001c";

  return (
    <header className="tt-header">
      <div className="tt-header-left">
        <div className="tt-brand">
          <TenderTentacleLogo />
          <span className="tt-brand-name">
            TENDER TENTACLE <span className="thin">| Bidding</span>
          </span>
        </div>
        <nav className="tt-nav">
          {SERVICES.map((s) => (
            <a key={s.name} href={s.path} className={s.active ? "active" : ""}>
              {s.name}
            </a>
          ))}
        </nav>
      </div>
      <div className="tt-header-right">
        <div className="tt-env" style={{ color: envColor, borderColor: `${envColor}66` }}>
          {envName} ENV
        </div>
        <div className="tt-online">
          <span className="dot" />
          <span>SYSTEM ONLINE</span>
        </div>
      </div>
    </header>
  );
}

function StatusTag({ status }: { status: string }) {
  return (
    <PTag variant={STATUS_VARIANT[status] ?? "secondary"} compact={true}>
      {status.replace("_", " ")}
    </PTag>
  );
}

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
    await api.uploadDocument(
      selected.id,
      file,
      item.requirement_type === "reference" ? "reference" : "supporting",
      item.id,
    );
    await open(selected.id);
  }

  return (
    <div className="app">
      <Header />
      {error && (
        <div className="error-bar" data-testid="error">
          <PInlineNotification state="error" heading="Request failed" description={error} dismissButton={false} />
        </div>
      )}
      <div className="content">
        <aside className="bid-list">
          <div className="bid-list-head">
            <PHeading size="small" tag="h2" className="section-label">
              Bids
            </PHeading>
            <PButton
              type="button"
              variant="secondary"
              icon="search"
              compact={true}
              hideLabel={true}
              onClick={() => setSelected(null)}
              data-testid="open-library"
            >
              Document Library
            </PButton>
          </div>
          <div data-testid="bid-list">
            {bids.map((b) => (
              <div
                key={b.id}
                data-testid="bid-list-item"
                className={`bid-card ${selected?.id === b.id ? "active" : ""}`}
                onClick={() => open(b.id)}
              >
                <div className="bid-card-top">
                  <StatusTag status={b.status} />
                  {b.portal_key && (
                    <PTag variant="secondary" compact={true}>
                      {b.portal_key}
                    </PTag>
                  )}
                </div>
                <PHeading size="small" tag="h3" className="bid-card-title">
                  {b.title}
                </PHeading>
                {b.customer && (
                  <div className="bid-card-meta">
                    <PIcon name="city" size="x-small" color="contrast-medium" />
                    <PText size="xs" color="contrast-medium">
                      {b.customer}
                    </PText>
                  </div>
                )}
              </div>
            ))}
          </div>
        </aside>

        <main className="workspace">
          {!selected && <Library />}
          {selected && (
            <Workspace
              bid={selected}
              onToggle={toggle}
              onUpload={upload}
              onReload={() => {
                open(selected.id);
                api.listBids().then(setBids).catch(() => {});
              }}
            />
          )}
        </main>
      </div>
    </div>
  );
}

const LIBRARY_KINDS = ["", "reference", "profile", "certificate", "declaration", "tender", "supporting"];

function Library() {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [client, setClient] = useState("");
  const [cpv, setCpv] = useState("");
  const [res, setRes] = useState<LibrarySearch | null>(null);
  const [busy, setBusy] = useState(false);

  const search = useCallback(() => {
    setBusy(true);
    api
      .searchLibrary({ q: q || undefined, kind: kind || undefined, client: client || undefined, cpv: cpv || undefined })
      .then(setRes)
      .catch(() => setRes(null))
      .finally(() => setBusy(false));
  }, [q, kind, client, cpv]);

  useEffect(search, []); // initial corpus listing

  return (
    <div data-testid="library">
      <div className="ws-header">
        <PHeading size="large" tag="h1">
          Document Library
        </PHeading>
        <PText size="small" color="contrast-medium">
          Search every document ever used in a bid — assemble your package from proven assets.
        </PText>
      </div>

      <div className="lib-filters">
        <input
          className="lib-input lib-q"
          placeholder="Topic — e.g. cloud migration references"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          data-testid="library-q"
        />
        <select className="lib-input" value={kind} onChange={(e) => setKind(e.target.value)} data-testid="library-kind">
          {LIBRARY_KINDS.map((k) => (
            <option key={k} value={k}>
              {k || "any kind"}
            </option>
          ))}
        </select>
        <input
          className="lib-input"
          placeholder="Client"
          value={client}
          onChange={(e) => setClient(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <input
          className="lib-input"
          placeholder="CPV code"
          value={cpv}
          onChange={(e) => setCpv(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <PButton type="button" variant="primary" icon="search" compact={true} loading={busy} onClick={search}>
          Search
        </PButton>
      </div>

      {res && (
        <div className="lib-results" data-testid="library-results">
          {res.results.length === 0 && (
            <PText color="contrast-medium">No documents match — try a broader topic or fewer filters.</PText>
          )}
          {res.results.map((r) => (
            <div key={r.fingerprint} className="item lib-hit" data-testid="library-hit">
              <div className="lib-hit-head">
                <PText weight="semibold" tag="span" className="doc-name">
                  {r.filename}
                </PText>
                <PTag variant="secondary" compact={true}>
                  {r.kind}
                </PTag>
                <PTag variant={r.sensitivity === "normal" ? "secondary" : "warning"} compact={true}>
                  {r.sensitivity}
                </PTag>
                {r.proven && (
                  <PTag variant="success" compact={true}>
                    proven · won
                  </PTag>
                )}
                {r.score > 0 && (
                  <PText size="xs" color="contrast-medium" tag="span">
                    relevance {r.score}
                  </PText>
                )}
              </div>
              {r.snippet && (
                <PText size="xs" color="contrast-medium" className="lib-snippet">
                  {r.snippet}
                </PText>
              )}
              <div className="lib-usages">
                {r.usages.map((u) => (
                  <PText size="xs" tag="span" key={u.bid_id} className="lib-usage">
                    {u.won ? "🏆 " : ""}
                    {u.bid_title}
                    {u.customer ? ` — ${u.customer}` : ""} ({u.bid_status})
                  </PText>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ScorePanel({ reco }: { reco: Recommendation }) {
  return (
    <div className="card" data-testid="score-panel">
      <div className="card-head">
        <PIcon name="chart" size="small" color="contrast-medium" />
        <PHeading size="small" tag="h3">
          Readiness Score
        </PHeading>
        <span className="score-total">{reco.score.total}</span>
      </div>
      {reco.score.criteria.map((c) => (
        <div key={c.key} className="score-row" title={c.detail}>
          <div className="score-row-head">
            <PText size="xs" tag="span">
              {c.label}
            </PText>
            <PText size="xs" color="contrast-medium" tag="span">
              {c.score} · w {Math.round(c.weight * 100)}%
            </PText>
          </div>
          <div className="score-bar">
            <div
              className={`score-fill ${c.score >= 65 ? "ok" : c.score >= 40 ? "warn" : "bad"}`}
              style={{ width: `${c.score}%` }}
            />
          </div>
          <PText size="xs" color="contrast-medium">
            {c.detail}
          </PText>
        </div>
      ))}
    </div>
  );
}

function Workspace({
  bid,
  onToggle,
  onUpload,
  onReload,
}: {
  bid: BidDetail;
  onToggle: (i: ChecklistItem) => void;
  onUpload: (i: ChecklistItem, f: File) => void;
  onReload: () => void;
}) {
  const gate = bid.formal_gate;
  const [reco, setReco] = useState<Recommendation | null>(null);
  const [matching, setMatching] = useState(false);
  const [promoting, setPromoting] = useState(false);

  const loadReco = useCallback(() => {
    api.getRecommendation(bid.id).then(setReco).catch(() => setReco(null));
  }, [bid.id]);

  // `bid` is a fresh object on every reload (toggle/upload → open()), so keying
  // the effect on it re-scores after each workspace change.
  useEffect(loadReco, [bid]);

  async function rematch() {
    setMatching(true);
    try {
      await api.matchDocuments(bid.id);
      loadReco();
    } finally {
      setMatching(false);
    }
  }

  // Exploring → draft: the human commits to actually preparing this bid.
  async function promote() {
    setPromoting(true);
    try {
      await api.setStatus(bid.id, { status: "draft", expected_version: bid.version });
      onReload();
    } finally {
      setPromoting(false);
    }
  }

  async function acceptEvidence(checklistItemId: string, documentId: string) {
    await api.acceptMatch(bid.id, { checklist_item_id: checklistItemId, document_id: documentId });
    onReload();
  }

  async function dismissEvidence(checklistItemId: string, documentId: string) {
    await api.rejectMatch(bid.id, {
      checklist_item_id: checklistItemId,
      document_id: documentId,
      reason: "dismissed in workspace",
    });
    loadReco();
  }

  const byKind = (k: string) =>
    bid.checklist_items.filter((i) => i.criterion_kind === k).sort((a, b) => a.order - b.order);

  return (
    <div data-testid="workspace">
      <div className="ws-header">
        <PHeading size="large" tag="h1">
          {bid.title}
        </PHeading>
        <div className="ws-sub">
          {bid.customer && (
            <span className="ws-customer">
              <PIcon name="city" size="x-small" color="contrast-medium" />
              <PText size="small" color="contrast-medium" tag="span">
                {bid.customer}
              </PText>
            </span>
          )}
          <StatusTag status={bid.status} />
          {bid.driver_user_id && (
            <PTag variant="primary" icon="user" compact={true}>
              Driver: {bid.driver_user_id}
            </PTag>
          )}
          {bid.lots_in_scope && bid.lots_in_scope.length > 0 && (
            <span data-testid="lots-badge">
              <PTag variant="primary" icon="stack" compact={true}>
                {bid.lots_in_scope.length} lots
              </PTag>
            </span>
          )}
        </div>
      </div>

      {bid.status === "exploring" && (
        <div className="gate" data-testid="exploring-banner">
          <PInlineNotification
            state="info"
            heading="Provisional workspace — marked interesting, not yet a bid"
            description="Requirements, matching and readiness were analysed automatically. Promote it to start real bid preparation, or let a no-bid triage archive it."
            dismissButton={false}
            actionLabel={promoting ? "Promoting…" : "Start bid preparation"}
            actionIcon="arrow-right"
            onAction={promote}
            data-testid="promote-action"
          />
        </div>
      )}

      {gate && (
        <div className="gate" data-testid="formal-gate">
          <PInlineNotification
            state={gate.ready ? "success" : "error"}
            heading={gate.ready ? "Formal pre-flight passed" : "Formal pre-flight blocked"}
            description={
              gate.ready
                ? "All formal items resolved — the bid clears the formalities gate."
                : `${gate.formal_open}/${gate.formal_total} formal items still open. Bids fail on formalities.`
            }
            dismissButton={false}
          />
        </div>
      )}

      {reco && (
        <div className="gate" data-testid="recommendation">
          <PInlineNotification
            state={RECO_STATE[reco.recommendation]}
            heading={`${RECO_HEADLINE[reco.recommendation]} (confidence ${Math.round(reco.confidence * 100)}%)`}
            description={reco.reasons.join(" · ")}
            dismissButton={false}
          />
        </div>
      )}

      <div className="panels">
        <section className="checklist">
          {["formal", "suitability", "award"].map((k) => {
            const items = byKind(k);
            if (items.length === 0) return null;
            const doneCount = items.filter((i) => i.status === "done").length;
            return (
              <div key={k} className="kind-group">
                <div className="kind-head">
                  <PHeading size="small" tag="h3">
                    {KIND_LABEL[k]}
                  </PHeading>
                  <PText size="xs" color="contrast-medium" tag="span">
                    {doneCount}/{items.length} done
                  </PText>
                </div>
                {items.map((item) => {
                  const done = item.status === "done";
                  return (
                    <div
                      key={item.id}
                      className={`item ${done ? "done-row" : ""}`}
                      data-testid="checklist-item"
                      data-kind={k}
                    >
                      <div className="item-main">
                        <button
                          type="button"
                          className={`item-check ${done ? "checked" : ""}`}
                          data-testid="item-checkbox"
                          aria-pressed={done}
                          aria-label={done ? "Mark open" : "Mark done"}
                          onClick={() => onToggle(item)}
                        >
                          <PIcon name={done ? "success" : "add"} color={done ? "success" : "contrast-medium"} size="small" />
                        </button>
                        <PText size="small" tag="span" className={done ? "done" : ""}>
                          {item.title}
                        </PText>
                      </div>
                      <div className="item-foot">
                        <label className="upload">
                          <PIcon name="upload" size="x-small" color="primary" />
                          <span>upload</span>
                          <input
                            type="file"
                            data-testid="item-upload"
                            style={{ display: "none" }}
                            onChange={(e) => e.target.files?.[0] && onUpload(item, e.target.files[0])}
                          />
                        </label>
                        {item.ai_verification && (
                          <PTag
                            variant={
                              item.ai_verification.status === "matched"
                                ? "success"
                                : item.ai_verification.status === "pending"
                                  ? "warning"
                                  : "error"
                            }
                            icon="ai-spark"
                            compact={true}
                          >
                            {item.ai_verification.status}
                          </PTag>
                        )}
                        {item.source_link && (
                          <PText size="xs" color="contrast-medium" tag="span" className="source">
                            {item.source_link}
                          </PText>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </section>

        <aside className="side-panels">
          {reco && <ScorePanel reco={reco} />}

          {reco && reco.reusable_evidence.length > 0 && (
            <div className="card" data-testid="reusable-evidence">
              <div className="card-head">
                <PIcon name="ai-spark" size="small" color="contrast-medium" />
                <PHeading size="small" tag="h3">
                  Reusable Evidence
                </PHeading>
              </div>
              <ul>
                {reco.reusable_evidence.map((m) => (
                  <li key={`${m.checklist_item_id}-${m.document_id}`} data-testid="evidence-row">
                    <PText size="xs" tag="span" className="doc-name">
                      {m.filename}
                    </PText>
                    <PText size="xs" color="contrast-medium" tag="span">
                      → {m.requirement} ({m.source})
                    </PText>
                    <span className="evidence-actions">
                      <PButton
                        type="button"
                        variant="primary"
                        icon="check"
                        compact={true}
                        hideLabel={true}
                        data-testid="evidence-accept"
                        onClick={() => acceptEvidence(m.checklist_item_id, m.document_id)}
                      >
                        Accept evidence
                      </PButton>
                      <PButton
                        type="button"
                        variant="secondary"
                        icon="close"
                        compact={true}
                        hideLabel={true}
                        data-testid="evidence-dismiss"
                        onClick={() => dismissEvidence(m.checklist_item_id, m.document_id)}
                      >
                        Dismiss
                      </PButton>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="card">
            <div className="card-head">
              <PIcon name="calendar" size="small" color="contrast-medium" />
              <PHeading size="small" tag="h3">
                Deadlines
              </PHeading>
            </div>
            <ul data-testid="deadlines">
              {bid.key_dates.length === 0 && (
                <li>
                  <PText size="small" color="contrast-medium">
                    No key dates.
                  </PText>
                </li>
              )}
              {bid.key_dates.map((d: KeyDate) => (
                <li key={d.id}>
                  <PText size="small" weight="semibold" tag="span" className="kd-kind">
                    {d.kind}
                  </PText>
                  <PText size="small" color="contrast-medium" tag="span" className="kd-date">
                    {d.date ? new Date(d.date).toLocaleDateString() : "—"}
                  </PText>
                  {typeof d.days_remaining === "number" && (
                    <PTag variant={d.days_remaining < 7 ? "error" : "secondary"} compact={true}>
                      {d.days_remaining}d
                    </PTag>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <div className="card-head">
              <PIcon name="document" size="small" color="contrast-medium" />
              <PHeading size="small" tag="h3">
                Documents
              </PHeading>
            </div>
            <ul data-testid="documents">
              {bid.documents.length === 0 && (
                <li>
                  <PText size="small" color="contrast-medium">
                    No documents yet.
                  </PText>
                </li>
              )}
              {bid.documents.map((doc) => (
                <li key={doc.id}>
                  <PText size="small" tag="span" className="doc-name">
                    {doc.filename}
                  </PText>
                  <PTag variant="secondary" compact={true}>
                    {doc.kind}
                  </PTag>
                  {doc.ai_verification && (
                    <PTag variant={doc.ai_verification.status === "matched" ? "success" : "error"} compact={true}>
                      {doc.ai_verification.status}
                    </PTag>
                  )}
                </li>
              ))}
            </ul>
            <div className="card-actions">
              <PButton
                type="button"
                variant="secondary"
                icon="refresh"
                compact={true}
                loading={matching}
                onClick={rematch}
                data-testid="match-button"
              >
                Match documents to requirements
              </PButton>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
