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
  type Matrix,
  type MatrixCategory,
  type MatrixEvaluation,
  type MatrixHistoryEntry,
  type PromptConfig,
  type Recommendation,
  type ServiceStats,
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

function Header({ view, setView }: { view: "bids" | "library" | "expert"; setView: (v: "bids" | "library" | "expert") => void }) {
  const host = typeof window !== "undefined" ? window.location.hostname : "";
  const isLocal = host.includes("localhost") || host.includes("127.0.0.1");
  const isTest = host.includes("-test");
  const envName = isLocal ? "LOCAL" : isTest ? "TEST" : "PROD";
  const envColor = isLocal ? "#8b8b9e" : isTest ? "#f59e0b" : "#d5001c";

  return (
    <>
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
      <div className="tt-sub-header">
        <button className={view === "bids" ? "active" : ""} onClick={() => setView("bids")}>Workspaces</button>
        <button className={view === "library" ? "active" : ""} onClick={() => setView("library")}>Document Library</button>
        <button className={view === "expert" ? "active" : ""} onClick={() => setView("expert")}>Expert Backend</button>
      </div>
    </>
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
  const [view, setView] = useState<"bids" | "library" | "expert">("bids");
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
      <Header view={view} setView={(v) => { setView(v); setSelected(null); }} />
      {error && (
        <div className="error-bar" data-testid="error">
          <PInlineNotification state="error" heading="Request failed" description={error} dismissButton={false} />
        </div>
      )}
      <div className={`content ${view === "bids" ? "split-view" : "full-view"}`}>
        {view === "bids" && (
          <aside className="bid-list">
            <div className="bid-list-head">
              <PHeading size="small" tag="h2" className="section-label">
                Bids
              </PHeading>
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
        )}

        <main className="workspace">
          {view === "expert" && <ExpertBackend />}
          {view === "library" && <Library />}
          {view === "bids" && selected && (
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
          {view === "bids" && !selected && (
            <div className="workspace-empty" style={{ padding: "40px", textAlign: "center" }}>
              <PText color="contrast-medium">Select a bid from the list to open its workspace.</PText>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

const WEIGHT_CHOICES = ["1", "2", "3", "4", "5"];

const PROMPT_LABEL: Record<string, string> = {
  bidding_required_documents: "Requirement detection prompt",
  bidding_deadlines: "Date detection prompt",
};

function KpiTiles() {
  const [stats, setStats] = useState<ServiceStats | null>(null);

  useEffect(() => {
    api.getStats().then(setStats).catch(() => setStats(null));
  }, []);

  if (!stats) return null;
  const tiles: [string, string | number][] = [
    ["Bids", stats.bids_total],
    ["Exploring", stats.bids_by_status["exploring"] ?? 0],
    ["Won", stats.bids_by_status["won"] ?? 0],
    ["Requirements detected", stats.requirements_detected],
    ["Checklist open", `${stats.checklist_items_open}/${stats.checklist_items_total}`],
    ["Deadlines ≤ 14d", stats.deadlines_due_14d],
    ["Corpus docs", stats.corpus_documents],
    ["Evaluated bids", stats.matrix_evaluated_bids],
    ["Human overrides", stats.human_overrides],
    ["Activity events", stats.activity_events],
  ];
  return (
    <div className="kpi-row" data-testid="expert-kpis">
      {tiles.map(([label, value]) => (
        <div key={label} className="kpi-tile">
          <span className="kpi-value">{value}</span>
          <PText size="xs" color="contrast-medium">
            {label}
          </PText>
        </div>
      ))}
    </div>
  );
}

function PromptsEditor() {
  const [configs, setConfigs] = useState<Record<string, PromptConfig>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api
      .getConfigs()
      .then((c) => {
        setConfigs(c);
        setDrafts(Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.prompt_template])));
      })
      .catch(() => setConfigs({}));
  }, []);

  async function save(category: string) {
    setMsg(null);
    try {
      const updated = await api.updateConfig(category, {
        prompt_template: drafts[category],
        change_summary: "Edited in expert backend",
      });
      setConfigs({ ...configs, [category]: updated });
      setMsg(`Prompt '${PROMPT_LABEL[category] ?? category}' saved (v${updated.version}).`);
    } catch (e) {
      setMsg(`Failed: ${String(e)}`);
    }
  }

  return (
    <div className="card expert-prompts" data-testid="expert-prompts">
      <div className="card-head">
        <PIcon name="document" size="small" color="contrast-medium" />
        <PHeading size="small" tag="h3">
          AI Prompts
        </PHeading>
      </div>
      <PText size="xs" color="contrast-medium" style={{ marginBottom: "16px", display: "block" }}>
        Synced to the AI connector before each extraction
      </PText>
      {msg && (
        <div className="gate">
          <PInlineNotification
            state={msg.startsWith("Failed") ? "error" : "success"}
            heading="Prompt config"
            description={msg}
            dismissButton={false}
          />
        </div>
      )}
      {Object.entries(configs).map(([category, cfg]) => (
        <div key={category} className="expert-prompt" data-testid="expert-prompt">
          <div className="expert-prompt-head">
            <PText size="small" weight="semibold" tag="span">
              {PROMPT_LABEL[category] ?? category}
            </PText>
            <PTag variant="secondary" compact={true}>
              {cfg.is_default ? "default" : `v${cfg.version}`}
            </PTag>
          </div>
          <textarea
            className="lib-input expert-prompt-text"
            rows={5}
            value={drafts[category] ?? ""}
            onChange={(e) => setDrafts({ ...drafts, [category]: e.target.value })}
          />
          <PButton type="button" variant="primary" compact={true} onClick={() => save(category)}>
            Save prompt
          </PButton>
        </div>
      ))}
    </div>
  );
}

function ExpertBackend() {
  const [matrix, setMatrix] = useState<Matrix | null>(null);
  const [history, setHistory] = useState<MatrixHistoryEntry[]>([]);
  const [missing, setMissing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [threshold, setThreshold] = useState("");
  const [name, setName] = useState("");
  const [draft, setDraft] = useState<{ headline: string; explanation: string; weight: string }>({
    headline: "",
    explanation: "",
    weight: "3",
  });

  const load = useCallback(() => {
    api
      .getMatrix()
      .then((m) => {
        setMatrix(m);
        setMissing(false);
        setThreshold(String(m.threshold));
        setName(m.name);
      })
      .catch(() => setMissing(true));
    api.getMatrixHistory().then(setHistory).catch(() => setHistory([]));
  }, []);

  useEffect(load, [load]);

  async function act(fn: () => Promise<Matrix>, okMsg: string) {
    setMsg(null);
    try {
      setMatrix(await fn());
      setMsg(okMsg);
      api.getMatrixHistory().then(setHistory).catch(() => {});
    } catch (e) {
      setMsg(`Failed: ${String(e)}`);
    }
  }

  if (missing) {
    return (
      <div data-testid="expert-backend">
        <PHeading size="large" tag="h1">
          Expert Backend
        </PHeading>
        <PText color="contrast-medium">
          No active decision matrix. Upload one in the Document Library to start.
        </PText>
        <KpiTiles />
        <PromptsEditor />
      </div>
    );
  }

  return (
    <div className="expert-container" data-testid="expert-backend">
      <div className="ws-header" style={{ marginBottom: "24px" }}>
        <PHeading size="large" tag="h1">
          Expert Backend — Decision Matrix
        </PHeading>
        <PText size="small" color="contrast-medium">
          Tune the bid/no-bid policy: threshold, categories, weights. Each category needs a headline and an
          explanation — the explanation is what the AI grounds its scoring on. Every change is versioned.
        </PText>
      </div>

      <KpiTiles />

      {msg && (
        <div className="gate" data-testid="expert-msg">
          <PInlineNotification
            state={msg.startsWith("Failed") ? "error" : "success"}
            heading="Decision matrix"
            description={msg}
            dismissButton={false}
          />
        </div>
      )}

      {matrix && (
        <>
          <div className="card">
            <div className="card-head">
              <PIcon name="wrench" size="small" color="contrast-medium" />
              <PHeading size="small" tag="h3">Matrix Settings</PHeading>
            </div>
            <div className="expert-settings">
              <label className="expert-field">
                <PText size="xs" color="contrast-medium">
                  Matrix name
                </PText>
                <input className="lib-input" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="expert-field">
                <PText size="xs" color="contrast-medium">
                  Threshold (max {matrix.max_points} = 5 × Σ weights)
                </PText>
                <input
                  className="lib-input"
                  type="number"
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                  data-testid="expert-threshold"
                />
              </label>
              <PTag variant="secondary" compact={true}>
                v{matrix.version}
              </PTag>
              <PButton
                type="button"
                variant="primary"
                compact={true}
                onClick={() =>
                  act(
                    () => api.updateMatrix({ name, threshold: Number(threshold), change_summary: "Edited in expert backend" }),
                    "Settings saved.",
                  )
                }
                data-testid="expert-save"
              >
                Save settings
              </PButton>
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <PIcon name="stack" size="small" color="contrast-medium" />
              <PHeading size="small" tag="h3">Categories</PHeading>
            </div>
            <div className="matrix-rows expert-rows" data-testid="expert-categories">
              {matrix.categories.map((c) => (
                <ExpertCategoryRow key={c.id} category={c} onAct={act} />
              ))}
            </div>

            <div className="expert-add">
              <input
                className="lib-input"
                placeholder="New category headline"
                value={draft.headline}
                onChange={(e) => setDraft({ ...draft, headline: e.target.value })}
                data-testid="expert-new-headline"
              />
              <input
                className="lib-input lib-q"
                placeholder="Explanation — the expert's intent, in prose (the AI scores against this)"
                value={draft.explanation}
                onChange={(e) => setDraft({ ...draft, explanation: e.target.value })}
              />
              <select
                className="lib-input"
                value={draft.weight}
                onChange={(e) => setDraft({ ...draft, weight: e.target.value })}
              >
                {WEIGHT_CHOICES.map((w) => (
                  <option key={w} value={w}>
                    w {w}
                  </option>
                ))}
              </select>
              <PButton
                type="button"
                variant="secondary"
                icon="add"
                compact={true}
                onClick={() =>
                  act(
                    () =>
                      api.addMatrixCategory({
                        headline: draft.headline,
                        explanation: draft.explanation || undefined,
                        weight: Number(draft.weight),
                      }),
                    "Category added.",
                  ).then(() => setDraft({ headline: "", explanation: "", weight: "3" }))
                }
                data-testid="expert-add"
              >
                Add category
              </PButton>
            </div>
          </div>

          <div className="card expert-history" data-testid="expert-history">
            <div className="card-head">
              <PIcon name="calendar" size="small" color="contrast-medium" />
              <PHeading size="small" tag="h3">
                History
              </PHeading>
            </div>
            <ul>
              {history.map((h) => (
                <li key={h.version}>
                  <PTag variant="secondary" compact={true}>
                    v{h.version}
                  </PTag>
                  <PText size="xs" tag="span">
                    {h.change_summary}
                  </PText>
                  <PText size="xs" color="contrast-medium" tag="span">
                    {h.created_by ?? "—"} · {new Date(h.created_at).toLocaleString()}
                  </PText>
                </li>
              ))}
            </ul>
          </div>

          <PromptsEditor />
        </>
      )}
    </div>
  );
}

function ExpertCategoryRow({
  category,
  onAct,
}: {
  category: MatrixCategory;
  onAct: (fn: () => Promise<Matrix>, okMsg: string) => Promise<void>;
}) {
  const [headline, setHeadline] = useState(category.headline);
  const [explanation, setExplanation] = useState(category.explanation ?? "");
  const [weight, setWeight] = useState(String(category.weight));
  const dirty =
    headline !== category.headline || explanation !== (category.explanation ?? "") || weight !== String(category.weight);

  return (
    <div className="matrix-row expert-row" data-testid="expert-category">
      <input className="lib-input" value={headline} onChange={(e) => setHeadline(e.target.value)} />
      <textarea
        className="lib-input expert-explanation"
        rows={2}
        value={explanation}
        placeholder="Explanation — what should the AI look for?"
        onChange={(e) => setExplanation(e.target.value)}
      />
      <select className="lib-input" value={weight} onChange={(e) => setWeight(e.target.value)}>
        {WEIGHT_CHOICES.map((w) => (
          <option key={w} value={w}>
            w {w}
          </option>
        ))}
      </select>
      <div className="expert-row-actions">
        <PButton
          type="button"
          variant="primary"
          compact={true}
          disabled={!dirty}
          onClick={() =>
            onAct(
              () => api.updateMatrixCategory(category.id, { headline, explanation, weight: Number(weight) }),
              `Category '${headline}' saved.`,
            )
          }
        >
          Save
        </PButton>
        <PButton
          type="button"
          variant="secondary"
          icon="delete"
          compact={true}
          hideLabel={true}
          onClick={() => onAct(() => api.deleteMatrixCategory(category.id), `Category '${headline}' removed.`)}
        >
          Delete
        </PButton>
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
  const [matrixMsg, setMatrixMsg] = useState<string | null>(null);

  async function uploadMatrix(file: File) {
    try {
      const m = await api.uploadMatrix(file);
      setMatrixMsg(`Matrix "${m.name}" active: ${m.categories.length} categories, threshold ${m.threshold}.`);
    } catch (e) {
      setMatrixMsg(`Upload failed: ${String(e)}`);
    }
  }

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
      <div className="ws-header lib-head">
        <div>
          <PHeading size="large" tag="h1">
            Document Library
          </PHeading>
          <PText size="small" color="contrast-medium">
            Search every document ever used in a bid — assemble your package from proven assets.
          </PText>
        </div>
        <label className="matrix-upload">
          <PButton
            type="button"
            variant="secondary"
            icon="upload"
            compact={true}
            onClick={(e) => ((e.currentTarget as HTMLElement).parentElement?.querySelector("input") as HTMLInputElement)?.click()}
            data-testid="matrix-upload"
          >
            Upload decision matrix
          </PButton>
          <input
            type="file"
            style={{ display: "none" }}
            accept=".md,.txt,.csv"
            onChange={(e) => e.target.files?.[0] && uploadMatrix(e.target.files[0])}
          />
        </label>
      </div>
      {matrixMsg && (
        <div className="gate" data-testid="matrix-upload-result">
          <PInlineNotification
            state={matrixMsg.startsWith("Upload failed") ? "error" : "success"}
            heading="Decision matrix"
            description={matrixMsg}
            dismissButton={false}
          />
        </div>
      )}

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

const OVERRIDE_CHOICES = ["—", "0", "1", "2", "3", "4", "5"];

function MatrixPanel({ bidId, onChanged }: { bidId: string; onChanged: () => void }) {
  const [ev, setEv] = useState<MatrixEvaluation | null>(null);
  const [missing, setMissing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .getMatrixEvaluation(bidId)
      .then((e) => {
        setEv(e);
        setMissing(false);
      })
      .catch(() => setMissing(true));
  }, [bidId]);

  useEffect(load, [load]);

  async function evaluate() {
    setBusy(true);
    try {
      setEv(await api.runMatrixEvaluation(bidId));
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function override(categoryId: string, value: string) {
    const score = value === "—" ? null : Number(value);
    setEv(await api.overrideMatrixCategory(bidId, categoryId, { score }));
    onChanged();
  }

  if (missing) return null; // no active matrix uploaded yet

  return (
    <div className="matrix" data-testid="matrix-panel">
      <div className="kind-head">
        <PHeading size="small" tag="h3">
          Decision Matrix — {ev?.matrix_name ?? "…"}
        </PHeading>
        {ev?.evaluated && ev.verdict && (
          <PTag variant={ev.verdict === "bid" ? "success" : "error"} compact={true} data-testid="matrix-verdict">
            {ev.total_points}/{ev.max_points} pts · threshold {ev.threshold} → {ev.verdict.replace("_", " ")}
          </PTag>
        )}
        <PButton
          type="button"
          variant="secondary"
          icon="refresh"
          compact={true}
          loading={busy}
          onClick={evaluate}
          data-testid="matrix-evaluate"
        >
          {ev?.evaluated ? "Re-evaluate with AI" : "Evaluate with AI"}
        </PButton>
      </div>
      {ev && (
        <div className="matrix-rows">
          {ev.categories.map((c) => (
            <div key={c.category_id} className="matrix-row" data-testid="matrix-category" title={c.explanation ?? ""}>
              <div className="matrix-cell name">
                <PText size="small" weight="semibold" tag="span">
                  {c.headline}
                </PText>
                <PTag variant="secondary" compact={true}>
                  w {c.weight}
                </PTag>
              </div>
              <div className="matrix-cell ai">
                <PText size="xs" color="contrast-medium" tag="span">
                  AI: {c.ai_score ?? "—"}
                </PText>
                {c.ai_rationale && (
                  <PText size="xs" color="contrast-medium" tag="span" className="matrix-rationale">
                    {c.ai_rationale}
                  </PText>
                )}
              </div>
              <div className="matrix-cell human">
                <label className="matrix-override">
                  <PText size="xs" color="contrast-medium" tag="span">
                    Override
                  </PText>
                  <select
                    className="lib-input matrix-select"
                    value={c.human_score === null ? "—" : String(c.human_score)}
                    onChange={(e) => override(c.category_id, e.target.value)}
                    data-testid="matrix-override"
                  >
                    {OVERRIDE_CHOICES.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                </label>
                {c.overridden_by && (
                  <PText size="xs" color="contrast-medium" tag="span">
                    by {c.overridden_by}
                  </PText>
                )}
              </div>
              <div className="matrix-cell pts">
                <PText size="small" weight="semibold" tag="span">
                  {c.weighted_points ?? "—"}
                </PText>
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

      <MatrixPanel bidId={bid.id} onChanged={loadReco} />

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
