"""AI backend for checklist generation, deadline extraction and document
verification.

Two backends behind one interface:
- MockAIClient (default): deterministic canned output derived from the tender
  snapshot, so the whole service runs on test data with no ai-connector.
- RealAIClient: calls the ai-connector (deferred wiring; v1 ships mock).

The generated checklist is split into the three procurement criterion kinds
(formal / suitability / award) because most public bids are lost on *formal*
grounds — the formal items drive the pre-flight gate.
"""

from __future__ import annotations

import re
from typing import Any

from core.config import AI_URL, MOCK_MODE
from core.logger import setup_logger

logger = setup_logger("bidding-ai")

# Criterion kinds (see DOMAIN.md). "formal" items are the pre-flight gate.
FORMAL = "formal"
SUITABILITY = "suitability"
AWARD = "award"


class AIClient:
    """Interface implemented by the mock and real backends."""

    async def generate_checklist(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def extract_deadlines(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def verify_document(self, requirement: str, doc_markdown: str) -> dict[str, Any]:
        raise NotImplementedError

    async def semantic_scores(self, query: str, texts: list[str]) -> list[float]:
        """Relevance (0–1) of each text to the query. Mock = token overlap; a real
        embedding backend slots in behind the same signature."""
        raise NotImplementedError


class MockAIClient(AIClient):
    """Deterministic, offline checklist/deadline/verification generation."""

    async def semantic_scores(self, query: str, texts: list[str]) -> list[float]:
        import re

        def toks(s: str) -> set[str]:
            return set(re.findall(r"[a-zä-üß]{4,}", (s or "").lower()))

        q = toks(query)
        if not q:
            return [0.0 for _ in texts]
        return [len(q & toks(t)) / len(q) for t in texts]

    async def generate_checklist(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        src = snapshot.get("source_ref") or snapshot.get("external_id") or "tender"
        corpus = self._corpus(snapshot)
        cited = f"{src} · documents"

        items: list[dict[str, Any]] = [
            # Formal — the pre-flight gate (signatures, forms, completeness, channel)
            self._item(
                FORMAL, "signature", "Signed declaration (Textform §126b BGB) with named authorised person", cited
            ),
            self._item(FORMAL, "mandatory_form", "Use the contracting authority's mandatory forms / VHB-Bund", cited),
            self._item(FORMAL, "completeness", "All requested documents present and correctly named", cited),
            self._item(FORMAL, "submission_channel", "Submit via the required portal channel and file format", cited),
            # Suitability (Eignung) — references, capacity, no-exclusion
            self._item(SUITABILITY, "reference", "3 comparable references from the last 3 years", cited),
            self._item(
                SUITABILITY, "profile", "Personnel concept: CVs matching the required qualification profiles", cited
            ),
            self._item(
                SUITABILITY, "certificate", "Valid certifications / register excerpts (e.g. trade register)", cited
            ),
            self._item(
                SUITABILITY,
                "self_declaration",
                "Self-declarations (minimum wage, sanctions, no exclusion grounds)",
                cited,
            ),
            # Award (Zuschlag) — how the bid is scored
            self._item(AWARD, "price_sheet", "Complete price sheet / Leistungsverzeichnis", cited),
            self._item(AWARD, "concept", "Solution / methodology concept addressing the award criteria", cited),
        ]
        # Consortium (§47 VgV): only when the corpus hints at it.
        if re.search(r"bietergemeinschaft|arge|nachunternehmer|subcontract", corpus, re.I):
            items.append(
                self._item(
                    FORMAL, "commitment_declaration", "§47 commitment declaration from each consortium partner", cited
                )
            )
        for i, it in enumerate(items):
            it["order"] = i
        return items

    async def extract_deadlines(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        src = f"{snapshot.get('source_ref', 'tender')} · notice"
        out: list[dict[str, Any]] = []
        if snapshot.get("deadline_at"):
            out.append({"kind": "submission", "date": snapshot["deadline_at"], "source_link": src})
        if snapshot.get("questions_deadline_at"):
            out.append({"kind": "questions", "date": snapshot["questions_deadline_at"], "source_link": src})
        return out

    async def verify_document(self, requirement: str, doc_markdown: str) -> dict[str, Any]:
        text = (doc_markdown or "").lower()
        req_terms = [w for w in re.split(r"\W+", requirement.lower()) if len(w) > 4]
        hits = sum(1 for w in req_terms if w in text)
        if not doc_markdown.strip():
            return {"status": "needs_review", "detail": "Empty document."}
        if hits >= max(1, len(req_terms) // 3):
            return {"status": "matched", "detail": f"Document mentions {hits} requirement terms."}
        return {"status": "gap", "detail": "Document does not clearly satisfy the requirement."}

    @staticmethod
    def _corpus(snapshot: dict[str, Any]) -> str:
        parts = [snapshot.get("title", ""), snapshot.get("description", ""), snapshot.get("document_text", "")]
        for lot in snapshot.get("lots", []) or []:
            parts.extend([lot.get("title", ""), lot.get("description", ""), lot.get("document_text", "")])
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _item(kind: str, req_type: str, title: str, source_link: str) -> dict[str, Any]:
        return {
            "criterion_kind": kind,
            "requirement_type": req_type,
            "title": title,
            "source_link": source_link,
            "status": "open",
            "ai_verification": None,
        }


class RealAIClient(AIClient):
    """Calls ai-connector. Deferred in v1 — falls back to mock behaviour."""

    def __init__(self) -> None:
        self._fallback = MockAIClient()
        logger.warning(f"RealAIClient targeting {AI_URL} is not wired in v1; using mock behaviour.")

    async def generate_checklist(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        return await self._fallback.generate_checklist(snapshot)

    async def extract_deadlines(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        return await self._fallback.extract_deadlines(snapshot)

    async def verify_document(self, requirement: str, doc_markdown: str) -> dict[str, Any]:
        return await self._fallback.verify_document(requirement, doc_markdown)

    async def semantic_scores(self, query: str, texts: list[str]) -> list[float]:
        return await self._fallback.semantic_scores(query, texts)


def get_ai_client() -> AIClient:
    return MockAIClient() if MOCK_MODE else RealAIClient()
