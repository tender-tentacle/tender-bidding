# 🤝 Bidding Microservice

> **Domain Type:** Core Domain (Collaborative Bid Preparation)
> **Port:** 8014 (Docker Compose service `bidding`)
> **Data:** own **isolated** database + Azure Blob (GDPR special-category documents)

Turns a tender/group triaged as a **bid** in the Enriching MS into a collaborative
**Bid Workspace**: an AI-generated, source-cited compliance checklist, deadline
tracking, and document collection worked by multiple collaborators. It exists
because public tenders are lost on **formal/document quality** (10–15% of bids are
formally excluded), and to break company silos by accumulating a reusable
cross-bid document corpus.

## v1 scope
Covers the *collaborative layer* of the 7-phase bid lifecycle (phases 2.3–2.7),
and models the procurement vocabulary of the deeper phases without implementing
them. **Deferred** to a later "Bid Domain": generative bid drafting, ESPD/EEE
UBL-XML + Schematron, UfAB scoring math, QES signature gatekeeper, XVergabe/TED
e-submission.

- **Checklist** split into **formal / suitability / award** criterion kinds, with a
  **formal pre-flight gate** (formal defects are the top exclusion cause).
- **Documents** — original in Blob, markdown + metadata in SQL; each classified by
  kind + **sensitivity** (normal/personal/special); AI verifies an upload against
  its checklist requirement.
- **Deadlines** (submission / questions / validity) with citations + countdown.
- **Collaboration** — driver + collaborators, per-item assignee, comments,
  optimistic concurrency (version → 409), append-only activity/audit log.
- **Win/Loss** capture (loss reason) — the learning loop for "why we lose".
- **Portal guide** — curated static registration/submission library + AI gap-fill.
- **Manual tender-doc upload + regenerate** (additive checklist diff) for when the
  crawler could not fetch the documents.

## Runs in real mode by default (no mocking)
`BIDDING_MOCK=0` (default) connects to the real AI connector and other services.
To run with mocked/offline services (canned AI + local-temp blob + SQLite), set `BIDDING_MOCK=1`.

```bash
# Backend
python3.12 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
BIDDING_MOCK=1 PYTHONPATH=. ../.venv/bin/python seed.py   # sample bids with mock mode
BIDDING_MOCK=0 PYTHONPATH=. ../.venv/bin/python main.py   # runs real mode on :8014

# Tests (hermetic, in-process ASGI + temp SQLite)
PYTHONPATH=. pytest            # unit + integration + pact
```

## Integration
Enriching relays a snapshot (tender + lots + parsed docs) to
`POST /api/v1/internal/bids/relay` when `triage_status` is set to `"bid"`
(best-effort; triage is unaffected if bidding is down). See
`tender-enriching/core/bidding_client.py`.

See [DOMAIN.md](DOMAIN.md) for the domain model and ubiquitous language.
