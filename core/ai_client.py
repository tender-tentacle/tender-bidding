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

    async def extract_required_documents(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def extract_bidding_deadlines(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def verify_document(self, requirement: str, document_markdown: str) -> dict[str, str]:
        raise NotImplementedError

    async def extract_document_metadata(self, target_text: str, document_markdown: str) -> dict[str, Any]:
        raise NotImplementedError

    async def semantic_scores(self, query: str, texts: list[str]) -> list[float]:
        """Relevance (0–1) of each text to the query. Mock = token overlap; a real
        embedding backend slots in behind the same signature."""
        raise NotImplementedError

    async def extract_decision_matrix(self, doc_markdown: str) -> dict[str, Any]:
        """Translate an uploaded decision-matrix document into weighted categories.

        Returns {"name", "threshold", "categories": [{"headline", "explanation", "weight"}]}.
        The explanation is the expert's intent in prose — it grounds the scoring.
        Weights are clamped to 1–5; threshold is in weighted points.
        """
        raise NotImplementedError

    async def score_category(self, category: dict[str, Any], bid_text: str, intel: dict[str, Any]) -> dict[str, Any]:
        """Score one decision category 0–5 for a bid. Returns {"score", "rationale"}."""
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

    # Fallback categories when the uploaded matrix has no parseable structure —
    # the classic German public-sector bid/no-bid criteria set. Each explanation
    # states the expert's intent in prose: it is what the AI scores against.
    DEFAULT_MATRIX_CATEGORIES = [
        {
            "headline": "Strategic fit",
            "explanation": "How well does the tender fit our portfolio, cluster strategy and target customers? "
            "High scores need an explicit link to a strategic cluster or a named target account.",
            "weight": 5,
        },
        {
            "headline": "Comparable references",
            "explanation": "Do we hold comparable references from the last 3 years for this service and sector? "
            "Score by how directly our references match subject, volume and customer type.",
            "weight": 4,
        },
        {
            "headline": "Delivery capacity",
            "explanation": "Team availability and required qualification profiles over the contract runtime. "
            "Low scores when key profiles are missing or already committed elsewhere.",
            "weight": 4,
        },
        {
            "headline": "Competitive environment",
            "explanation": "Incumbent advantage and the number of likely competitors on this notice. "
            "Fewer credible competitors and no entrenched incumbent mean a higher score.",
            "weight": 3,
        },
        {
            "headline": "Profitability",
            "explanation": "Expected margin, price pressure and framework conditions. "
            "Score low when the award is price-dominated or terms squeeze the margin.",
            "weight": 3,
        },
        {
            "headline": "Formal & legal risk",
            "explanation": "Contract terms, liability exposure and certifications we lack. "
            "Score low when mandatory certificates or unacceptable contract clauses block us.",
            "weight": 4,
        },
    ]

    async def extract_decision_matrix(self, doc_markdown: str) -> dict[str, Any]:
        """Deterministic translation: parses `Headline (weight N): explanation` lines
        and a `threshold: N` line; falls back to the default category set."""
        text = doc_markdown or ""
        categories: list[dict[str, Any]] = []
        for m in re.finditer(r"(?m)^[-*•]?\s*(.+?)\s*\((?:weight|gewicht)\s*[:=]?\s*(\d)\)\s*:?\s*(.*)$", text, re.I):
            categories.append(
                {
                    "headline": m.group(1).strip()[:255],
                    "explanation": m.group(3).strip() or None,
                    "weight": min(5, max(1, int(m.group(2)))),
                }
            )
        if not categories:
            categories = [dict(c) for c in self.DEFAULT_MATRIX_CATEGORIES]

        max_points = 5 * sum(c["weight"] for c in categories)
        th = re.search(r"(?:threshold|schwelle|schwellwert)\s*[:=]?\s*(\d+)", text, re.I)
        threshold = min(max_points, int(th.group(1))) if th else round(max_points * 0.6)

        name_match = re.search(r"(?m)^#*\s*(.+matrix.*)$", text, re.I)
        return {
            "name": (name_match.group(1).strip() if name_match else "Bid/No-Bid Decision Matrix")[:255],
            "threshold": threshold,
            "categories": categories,
        }

    async def score_category(self, category: dict[str, Any], bid_text: str, intel: dict[str, Any]) -> dict[str, Any]:
        """Deterministic 0–5 score with a transparent rationale.

        Grounded on headline + the expert's explanation: competition-flavoured
        categories are driven by portal intelligence (more likely competitors →
        lower score); everything else by evidence overlap between the category's
        explanation and the bid's text corpus.
        """
        name = (category.get("headline") or "").lower()
        desc = (category.get("explanation") or "").lower()

        if any(w in name + desc for w in ("competit", "wettbewerb", "konkurren")):
            n = len(intel.get("competitors", []))
            score = max(0, 5 - n)
            names = ", ".join(c["name"] for c in intel.get("competitors", [])[:3]) or "none found"
            portals = "/".join(intel.get("source_portals", []))
            return {
                "score": score,
                "rationale": f"{n} likely competitor(s) via {portals}: {names}. Fewer competitors → higher score.",
            }

        terms = [w for w in re.split(r"\W+", f"{name} {desc}") if len(w) > 4]
        text = (bid_text or "").lower()
        hits = sorted({w for w in terms if w in text})
        score = min(5, len(hits) + (1 if hits else 0))
        detail = f"evidence terms found: {', '.join(hits)}" if hits else "no supporting evidence found in bid corpus"
        return {"score": score, "rationale": f"{len(hits)} of {len(set(terms))} category terms covered — {detail}."}

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

        # Parse ESPD 4C structure from selection_criteria
        sel_criteria = snapshot.get("selection_criteria") or {}
        tech_ability = sel_criteria.get("technical_ability") or {}

        # 4C.1/4C.2 References
        if tech_ability.get("references"):
            items.append(
                self._item(
                    SUITABILITY,
                    "reference",
                    "References / Past Performance (ESPD 4C.1)",
                    cited,
                    metadata_json={"espd_part": "4C.1", "references": tech_ability.get("references")},
                )
            )

        # 4C.6 Profiles/CVs
        if tech_ability.get("educational_and_professional_qualifications"):
            items.append(
                self._item(
                    SUITABILITY,
                    "profile",
                    "Personnel CVs / Qualifications (ESPD 4C.6)",
                    cited,
                    metadata_json={
                        "espd_part": "4C.6",
                        "qualifications": tech_ability.get("educational_and_professional_qualifications"),
                    },
                )
            )

        # 4C.8 Manpower
        if tech_ability.get("average_annual_manpower"):
            items.append(
                self._item(
                    SUITABILITY,
                    "capacity",
                    "Average Annual Manpower (ESPD 4C.8)",
                    cited,
                    metadata_json={"espd_part": "4C.8", "manpower": tech_ability.get("average_annual_manpower")},
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

    async def extract_document_metadata(self, target_text: str, document_markdown: str) -> dict[str, Any]:
        """Mock extraction."""
        return {
            "extracted_metadata": {
                "espd_part": "4C.1",
                "project_title": "Mock Project",
                "person_name": "Max Mustermann",
            }
        }

    async def extract_required_documents(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        base_docs: list[dict[str, Any]] = [
            {
                "id": "doc_handelsregister",
                "document_name": "Handelsregisterauszug",
                "description": "Aktueller Auszug aus dem Handelsregister (nicht älter als 3 Monate).",
                "category": "suitability",
                "short_summary": "Handelsregisterauszug nicht älter als 3 Monate.",
                "quote_original": "Zum Nachweis der Eignung ist ein aktueller Auszug aus dem Handelsregister (nicht älter als drei Monate ab dem Tag der Angebotsabgabe) vorzulegen.",
                "source_doc_name": "Ausschreibungsunterlagen.pdf",
                "is_mandatory": True,
            },
            {
                "id": "doc_referenz_1",
                "document_name": "Referenz 1 - Netzwerktechnik",
                "description": "Erste vergleichbare Referenz über Netzwerktechnik/Dienstleistungen aus den letzten drei Jahren.",
                "category": "suitability",
                "short_summary": "Vergleichbare Referenz über Netzwerktechnik der letzten 3 Jahre.",
                "quote_original": "Der Bieter muss mindestens drei Referenzen über vergleichbare Leistungen aus den letzten 3 Jahren vorweisen.",
                "source_doc_name": "Vergabeunterlagen.pdf",
                "is_mandatory": False,
            },
            {
                "id": "doc_referenz_2",
                "document_name": "Referenz 2 - Projektkomplexität",
                "description": "Zweite vergleichbare Referenz mit ähnlicher Projektkomplexität aus den letzten drei Jahren.",
                "category": "suitability",
                "short_summary": "Referenz über vergleichbare Komplexität der letzten 3 Jahre.",
                "quote_original": "Der Bieter muss mindestens drei Referenzen über vergleichbare Leistungen aus den letzten 3 Jahren vorweisen.",
                "source_doc_name": "Vergabeunterlagen.pdf",
                "is_mandatory": False,
            },
            {
                "id": "doc_cv_project_lead",
                "document_name": "Lebenslauf Projektleiter",
                "description": "Lebenslauf des vorgesehenen Projektleiters.",
                "category": "suitability",
                "short_summary": "Lebenslauf Projektleiter",
                "quote_original": "Projektteam CVs: Lebensläufe der vorgesehenen Schlüsselpersonen mit Nachweis der geforderten Zertifizierungen.",
                "source_doc_name": "Projektbeschreibung.pdf",
                "is_mandatory": True,
            },
            {
                "id": "doc_cv_senior_dev_1",
                "document_name": "Lebenslauf Senior-Entwickler 1",
                "description": "Lebenslauf des ersten Senior-Entwicklers mit Nachweis relevanter Fachzertifikate.",
                "category": "suitability",
                "short_summary": "Lebenslauf des ersten Senior-Entwicklers mit Zertifikatsnachweis.",
                "quote_original": "Projektteam CVs: Lebensläufe der vorgesehenen Schlüsselpersonen mit Nachweis der geforderten Zertifizierungen.",
                "source_doc_name": "Projektbeschreibung.pdf",
                "is_mandatory": True,
            },
            {
                "id": "doc_cv_senior_dev_2",
                "document_name": "Lebenslauf Senior-Entwickler 2",
                "description": "Lebenslauf des zweiten Senior-Entwicklers mit Nachweis relevanter Fachzertifikate.",
                "category": "suitability",
                "short_summary": "Lebenslauf des zweiten Senior-Entwicklers mit Zertifikatsnachweis.",
                "quote_original": "Projektteam CVs: Lebensläufe der vorgesehenen Schlüsselpersonen mit Nachweis der geforderten Zertifizierungen.",
                "source_doc_name": "Projektbeschreibung.pdf",
                "is_mandatory": True,
            },
            {
                "id": "doc_haftpflicht",
                "document_name": "Haftpflichtversicherung",
                "description": "Nachweis einer bestehenden Betriebshaftpflichtversicherung mit ausreichender Deckung.",
                "category": "suitability",
                "short_summary": "Nachweis einer ausreichenden Betriebshafpflichtversicherung.",
                "quote_original": "Haftpflichtversicherung: Nachweis einer bestehenden Betriebshaftpflichtversicherung mit ausreichender Deckung.",
                "source_doc_name": "Ausschreibungsunterlagen.pdf",
                "is_mandatory": True,
            },
            {
                "id": "doc_eigenerklaerung_ausschluss",
                "document_name": "Eigenerklärung Ausschlussgründe",
                "description": "Eigenerklärung, dass keine Ausschlussgründe nach VgV vorliegen.",
                "category": "self-declaration",
                "short_summary": "Eigenerklärung zu Nichtvorliegen von Ausschlussgründen.",
                "quote_original": "Eigenerklärung, dass keine Ausschlussgründe nach §§ 123, 124 GWB vorliegen.",
                "source_doc_name": "Eigenerklaerungen.pdf",
                "is_mandatory": True,
            },
            {
                "id": "doc_eigenerklaerung_mindestlohn",
                "document_name": "Eigenerklärung Mindestlohn",
                "description": "Eigenerklärung zur Einhaltung des Mindestlohngesetzes (MiLoG).",
                "category": "self-declaration",
                "short_summary": "MiLoG-Einhaltungserklärung.",
                "quote_original": "Eigenerklärung zur Einhaltung des Mindestlohngesetzes (MiLoG) sowie landesspezifischer Tariftreuevorgaben.",
                "source_doc_name": "Eigenerklaerungen.pdf",
                "is_mandatory": True,
            },
            {
                "id": "doc_preisblatt",
                "document_name": "Preisblatt",
                "description": "Vollständig ausgefülltes Preisblatt im PDF- und GAEB-Format.",
                "category": "proposal",
                "short_summary": "Ausgefülltes Preisblatt (PDF / GAEB).",
                "quote_original": "Das Preisblatt ist vollständig auszufüllen und als PDF sowie im GAEB-Format hochzuladen.",
                "source_doc_name": "Preisblatt.pdf",
                "is_mandatory": True,
            },
            {
                "id": "doc_leistungskonzept",
                "document_name": "Leistungskonzept",
                "description": "Detaillierte Beschreibung des angebotenen Konzepts zur Umsetzung des Leistungsverzeichnisses.",
                "category": "proposal",
                "short_summary": "Konzeptbeschreibung zur Umsetzung des LV.",
                "quote_original": "Der Bieter hat ein detailliertes Leistungskonzept einzureichen, das auf die Anforderungen der Leistungsbeschreibung eingeht.",
                "source_doc_name": "Vergabeunterlagen.pdf",
                "is_mandatory": True,
            },
        ]

        # Parse ESPD 4C structure from selection_criteria and add as RequiredDocuments
        sel_criteria = snapshot.get("selection_criteria") or {}
        tech_ability = sel_criteria.get("technical_ability") or {}

        if tech_ability.get("references"):
            base_docs.append(
                {
                    "id": "doc_espd_references",
                    "document_name": "ESPD 4C.1 - References",
                    "description": "Nachweis von Referenzen entsprechend ESPD 4C.",
                    "category": "suitability",
                    "short_summary": "Referenzen gemäß ESPD",
                    "quote_original": "Gemäß ESPD Anforderung 4C.1",
                    "source_doc_name": "ESPD.xml",
                    "is_mandatory": True,
                    "extracted_metadata": {"espd_part": "4C.1", "references": tech_ability.get("references")},
                }
            )

        if tech_ability.get("educational_and_professional_qualifications"):
            base_docs.append(
                {
                    "id": "doc_espd_profiles",
                    "document_name": "ESPD 4C.6 - Qualifications",
                    "description": "Nachweis von Qualifikationen entsprechend ESPD 4C.",
                    "category": "suitability",
                    "short_summary": "Qualifikationen gemäß ESPD",
                    "quote_original": "Gemäß ESPD Anforderung 4C.6",
                    "source_doc_name": "ESPD.xml",
                    "is_mandatory": True,
                    "extracted_metadata": {
                        "espd_part": "4C.6",
                        "qualifications": tech_ability.get("educational_and_professional_qualifications"),
                    },
                }
            )

        return base_docs

    async def extract_bidding_deadlines(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        out = []
        sub_date = snapshot.get("deadline_at")
        if sub_date:
            out.append({"kind": "submission", "date": sub_date, "source_link": "notice"})
        else:
            out.append(
                {
                    "kind": "submission",
                    "date": (now + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
                    "source_link": "notice",
                }
            )

        q_date = snapshot.get("questions_deadline_at") or snapshot.get("questions_deadline")
        if q_date:
            out.append({"kind": "questions", "date": q_date, "source_link": "notice"})
        else:
            out.append(
                {
                    "kind": "questions",
                    "date": (now + timedelta(days=15)).isoformat().replace("+00:00", "Z"),
                    "source_link": "notice",
                }
            )

        out.append(
            {
                "kind": "registration",
                "date": (now + timedelta(days=10)).isoformat().replace("+00:00", "Z"),
                "source_link": "notice",
            }
        )
        out.append(
            {
                "kind": "validity",
                "date": (now + timedelta(days=90)).isoformat().replace("+00:00", "Z"),
                "source_link": "notice",
            }
        )
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
    def _item(
        kind: str, req_type: str, title: str, source_link: str, metadata_json: dict | None = None
    ) -> dict[str, Any]:
        return {
            "criterion_kind": kind,
            "requirement_type": req_type,
            "title": title,
            "source_link": source_link,
            "status": "open",
            "ai_verification": None,
            "metadata_json": metadata_json,
        }


REQUIRED_DOCUMENTS_PROMPT = """
Du bist ein Experte für öffentliche Ausschreibungen.
Analysiere die bereitgestellten Ausschreibungsdaten (und eventuelle Dokumententexte) und extrahiere eine Liste aller erforderlichen Nachweise und Unterlagen (Required Documents), die der Bieter einreichen muss.
Kategorisiere jedes Dokument in eines der folgenden:
- suitability (Eignungsnachweise wie Handelsregister, Referenzen, CVs)
- self-declaration (Eigenerklärungen wie Mindestlohn, Sanktionen, keine Ausschlussgründe)
- proposal (Angebotsunterlagen wie Preisblatt, Konzept, Formblätter)
- consortium (Konsortium / Nachunternehmer Erklärungen)

Extrahiere für jedes Dokument zusätzlich:
- id: Ein eindeutiger String-Identifikator (z. B. "doc_handelsregister" oder "doc_referenz_1").
- short_summary: Eine prägnante, ein- oder zweisätzige Zusammenfassung der Anforderungen für dieses Dokument auf Deutsch.
- quote_original: Das exakte Zitat aus den Ausschreibungstexten oder Dokumententexten auf Deutsch, das diese Dokumentenanforderung belegt.
- source_doc_name: Der Dateiname oder die URL des Dokuments, aus dem das Zitat stammt (z. B. "Vergabeunterlagen.pdf"). Wenn die Quelle die Hauptausschreibung ist, gib "notice" an.
- is_mandatory: Ein boolescher Wert (true oder false). Setze auf true, wenn das Dokument zwingend/obligatorisch einzureichen ist (z. B. Handelsregisterauszug, Preisblatt). Setze auf false, wenn das Dokument nur empfohlen oder optional ist (z. B. freiwillige Referenzen).

Antworte ausschließlich im JSON-Format.
Struktur:
{"documents": [{"id": "...", "document_name": "...", "description": "...", "category": "suitability|self-declaration|proposal|consortium", "short_summary": "...", "quote_original": "...", "source_doc_name": "...", "is_mandatory": true}]}
""".strip()

DEADLINES_PROMPT = """
Du bist ein Experte für öffentliche Ausschreibungen.
Extrahiere alle Fristen (Deadlines) für dieses Vergabeverfahren aus den bereitgestellten Daten.
Bestimme die Fristen für:
- submission: Abgabefrist für Angebote / Teilnahmeanträge
- questions: Frist für Bieterfragen
- registration: Registrierungsfrist / Teilnahmeantragsfrist
- validity: Bindefrist / Zuschlagsfrist

Antworte ausschließlich im JSON-Format.
Struktur:
{"deadlines": [{"kind": "submission|questions|registration|validity", "date": "ISO8601-Format", "source_link": "notice"}]}
""".strip()

ESPD_DOCUMENT_EXTRACTION_PROMPT = """
Du bist ein Experte für öffentliche Ausschreibungen (Public Procurement) und den ESPD-Standard (European Single Procurement Document).
Deine Aufgabe ist es, strukturierte Metadaten aus dem hochgeladenen Dokument zu extrahieren, das ein Bieter als Nachweis eingereicht hat.
Die Anforderung (Requirement Target) gibt dir Kontext darüber, was das Dokument nachweisen soll (z.B. eine Referenz oder ein Profil).

Extrahiere alle zutreffenden Felder aus ESPD Part 4C (Technical and professional ability):
- 4C.1/4C.2 (References): project_title, amount, currency, start_date, end_date, recipient_name, is_public_buyer (boolean)
- 4C.3 (Technicians): technician_name, technical_unit_description
- 4C.4 (Supply Chain): supply_chain_system_description
- 4C.5 (Quality Control): quality_control_institute_name
- 4C.6 (Personnel/Profiles): person_name, proposed_role, educational_qualifications (list), professional_qualifications (list), years_of_experience (int)
- 4C.7 (Environmental): environmental_management_measures
- 4C.8 (Manpower): average_annual_manpower (int), managerial_staff_count (int)
- 4C.9 (Tools/Equipment): equipment_description
- 4C.10 (Subcontracting): subcontracting_proportion (string or float)

Zusätzlich für 4A (Suitability) / 4B (Financial):
- 4A: trade_register_number, legal_form
- 4B: yearly_turnover, insurance_amount

Antworte ausschließlich im JSON-Format. Extrahiere nur die Felder, die im Dokument eindeutig erwähnt werden.
Struktur:
{"extracted_metadata": {"espd_part": "4C.1", "project_title": "...", "amount": 50000, "currency": "EUR", "person_name": "...", "years_of_experience": 5}}
""".strip()


async def _configured_prompt(category: str) -> str:
    """Expert-edited template from the config API, or the hardcoded default."""
    # Function-level imports: services.prompt_config imports this module's defaults.
    from services.prompt_config import current_template

    from core.database import SessionLocal

    try:
        async with SessionLocal() as db:
            return await current_template(db, category)
    except Exception as e:
        logger.warning(f"Could not read configured prompt for {category}; using default: {e}")
        return {
            "bidding_required_documents": REQUIRED_DOCUMENTS_PROMPT,
            "bidding_deadlines": DEADLINES_PROMPT,
            "bidding_espd_extraction": ESPD_DOCUMENT_EXTRACTION_PROMPT,
        }.get(category, "")


async def _sync_prompt(prompt_id: str, system_message: str):
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{AI_URL}/api/prompts",
                json={
                    "id": prompt_id,
                    "name": prompt_id.replace("_", " ").title(),
                    "slug": prompt_id,
                    "system_message": system_message,
                    "version": "1.0.0",
                    "temperature": 0.1,
                    "model": "gpt-4o",
                    "description": f"Seeded from tender-bidding for {prompt_id}",
                },
            )
    except Exception as e:
        logger.warning(f"Failed to sync prompt {prompt_id} to AI service: {e}")


class RealAIClient(AIClient):
    """Calls ai-connector. Deferred in v1 — falls back to mock behaviour."""

    def __init__(self) -> None:
        self._fallback = MockAIClient()
        logger.warning(f"RealAIClient targeting {AI_URL} is not wired in v1; using mock behaviour.")

    async def generate_checklist(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        return await self._fallback.generate_checklist(snapshot)

    async def extract_deadlines(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        return await self._fallback.extract_deadlines(snapshot)

    async def extract_required_documents(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        import httpx

        try:
            # Sync the expert-edited prompt (falls back to the default) to the AI connector.
            await _sync_prompt("bidding_required_documents", await _configured_prompt("bidding_required_documents"))
            await _sync_prompt("bidding_deadlines", await _configured_prompt("bidding_deadlines"))
            await _sync_prompt("bidding_espd_extraction", await _configured_prompt("bidding_espd_extraction"))
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{AI_URL}/api/inference",
                    json={
                        "prompt_id": "bidding_required_documents",
                        "tender_data": snapshot,
                        "output_structure": {
                            "documents": [
                                {
                                    "id": "str",
                                    "document_name": "str",
                                    "description": "str",
                                    "category": "str",
                                    "short_summary": "str",
                                    "quote_original": "str",
                                    "source_doc_name": "str",
                                    "is_mandatory": "bool",
                                }
                            ]
                        },
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        docs = data.get("data", {}).get("documents")
                        if docs is not None:
                            return docs
                raise RuntimeError(f"AI service returned status code {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error calling AI for required documents: {e}")
            raise

    async def extract_bidding_deadlines(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        import httpx

        try:
            # Sync the expert-edited prompt (falls back to the default) to the AI connector.
            await _sync_prompt("bidding_deadlines", await _configured_prompt("bidding_deadlines"))
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{AI_URL}/api/inference",
                    json={
                        "prompt_id": "bidding_deadlines",
                        "tender_data": snapshot,
                        "output_structure": {"deadlines": [{"kind": "str", "date": "str", "source_link": "str"}]},
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        deadlines = data.get("data", {}).get("deadlines")
                        if deadlines is not None:
                            return deadlines
                raise RuntimeError(f"AI service returned status code {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Error calling AI for deadlines: {e}")
            raise

    async def verify_document(self, requirement: str, doc_markdown: str) -> dict[str, Any]:
        return await self._fallback.verify_document(requirement, doc_markdown)

    async def semantic_scores(self, query: str, texts: list[str]) -> list[float]:
        return await self._fallback.semantic_scores(query, texts)

    async def extract_decision_matrix(self, doc_markdown: str) -> dict[str, Any]:
        return await self._fallback.extract_decision_matrix(doc_markdown)

    async def score_category(self, category: dict[str, Any], bid_text: str, intel: dict[str, Any]) -> dict[str, Any]:
        return await self._fallback.score_category(category, bid_text, intel)


def get_ai_client() -> AIClient:
    return MockAIClient() if MOCK_MODE else RealAIClient()
