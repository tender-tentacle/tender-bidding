# Bidding — Domain Model & Ubiquitous Language

**Bounded context:** Collaborative Bid Preparation (Core Domain). Upstream =
Enriching (Anti-Corruption Layer: a snapshot is copied in, never a shared DB).

## Ubiquitous language
- **Bid** — the aggregate root. One procurement notice → one Bid, coordinated by a
  single **driver**. A Bid may target specific **lots** (`lots_in_scope`).
- **Driver** — the one collaborator who coordinates the whole bid across all lots.
- **Collaborator** — a user working the bid (lead / contributor / reviewer).
- **Checklist item** — a requirement extracted from the tender documents, of a
  **criterion kind**:
  - **formal** (Formalkriterien) — signatures, mandatory forms, completeness,
    submission channel. These drive the **formal pre-flight gate**; formal
    defects cause most exclusions.
  - **suitability** (Eignungskriterien) — references, capacity, certificates,
    no-exclusion grounds.
  - **award** (Zuschlagskriterien) — price sheet, concept — how the bid is scored.
- **Document** — a `BidDocument`: original bytes in Blob + a markdown rendering +
  metadata. Classified by **kind** (tender / reference / profile / supporting) and
  **sensitivity** (normal / personal / **special** = GDPR special-category, e.g.
  court documents, worker CVs).
- **Key date** — submission / questions / validity (Bindefrist) deadline.
- **Activity** — append-only audit event (also the GDPR access trail).
- **Portal guide** — curated static registration/submission guidance per portal.

## Aggregate & invariants
- `source_ref` (the enriching external_id / group id) is unique → relay is
  **idempotent**.
- **Optimistic concurrency**: bid-level mutations carry the read `version`; a
  mismatch is a 409 (reload).
- A `lost` bid must record a **loss_reason** (formal / price / quality /
  reference_gap / other) — the Win/Loss learning loop.
- Documents keep the original in Blob and never in the DB.

## Data isolation & GDPR
This service stores personal and special-category documents, so it runs on its
**own dedicated database** (a separate Azure SQL server in production) with its
own credential, and originals live in Azure Blob. Access is per-bid via
collaborators; every mutation is written to the append-only `BidActivity` log.

## Deliberately out of v1 (modelled, not implemented)
Generative bid drafting; ESPD/EEE UBL-2.x XML + Schematron validation; UfAB VI
scoring math; QES signature gatekeeper; XVergabe SOAP + TED eSubmission. The
vocabulary above (criterion kinds, textform-vs-QES, consortium/§47) is present so
the later "Bid Domain" service can build on it without a rewrite.
