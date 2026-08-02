"""Versioned AI-prompt configuration (mirrors the enriching config API).

The expert edits the extraction prompts here; RealAIClient syncs the *current*
template to the AI connector before each inference. Until an expert edits a
category, the hardcoded default from core.ai_client applies.
"""

from __future__ import annotations

from typing import Any

from core.ai_client import DEADLINES_PROMPT, REQUIRED_DOCUMENTS_PROMPT
from models.bid import PromptConfig, PromptConfigHistory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PROMPTS: dict[str, str] = {
    "bidding_required_documents": REQUIRED_DOCUMENTS_PROMPT,
    "bidding_deadlines": DEADLINES_PROMPT,
    "bidding_historical_evidence": "Du bist ein Research-Agent. Bitte recherchiere oder schätze als 'on the fly crawler' historische Tender-Daten für den Kunden '{buyer_name}'. Extrahiere oder leite fundierte Annahmen für die Felder 'award_median', 'accepted_rate_corridor' und 'budget_amendment_rate' ab. Gib die Antwort zwingend auf Deutsch im JSON-Format zurück, mit exakt diesen drei Feldern.",
    "bidding_strategy": "Du bist ein Bid Manager, der die 'Preisgestaltung (Pricing Quality)' für eine neue Ausschreibung von {buyer_name} bewertet (Wert: {current_value}, Verhältnis Preis/Qualität: {current_ratio}). Vergleiche dies mit der historischen Baseline des Kunden: {historical_pricing_payload}. Gib eine strategische Empfehlung ab, wie unser kommerzielles Angebot strukturiert werden sollte, welche Tagessätze wir anpeilen sollten und ob Risikopuffer eingeplant werden müssen. Antworte zwingend auf Deutsch in allen JSON-Feldern (strategy, strengths, warnings).",
    "bidding_financial_summary": "Du bist ein Analyst für finanzielle Stabilität. Analysiere die extrahierten Finanzdaten des Unternehmens '{company_name}': {financial_data}. Erstelle eine Zusammenfassung der finanziellen Stabilität und langfristigen Lebensfähigkeit. Antworte auf Deutsch und gib ein JSON zurück mit dem Feld 'summary'.",
    "bidding_hiring_summary": "Du bist ein HR-Analyst. Analysiere die extrahierten offenen Stellenangebote des Unternehmens '{company_name}': {jobs_data}. Fasse die aktuellen Einstellungstrends, gesuchten Profile und den mutmaßlichen strategischen Fokus zusammen. Antworte auf Deutsch und gib ein JSON zurück mit dem Feld 'summary'.",
    "bidding_buyer_reputation": "Du bist ein Experte für Employer Branding. Analysiere die Kununu-Bewertungen und Stimmungsdaten des Unternehmens '{company_name}': {mood_data}. Fasse die Reputation und Stimmung der Mitarbeiter zusammen. Antworte auf Deutsch und gib ein JSON zurück mit dem Feld 'summary'.",
    "bidding_mhp_reputation": "Du bist ein Strategieberater bei MHP. Erstelle eine strategische Zusammenfassung unserer (MHP's) Reputation und Markendurchdringung im speziellen Geschäftsumfeld des Kunden '{company_name}' basierend auf unseren historischen Erfolgen und generellem Profil. Antworte auf Deutsch und gib ein JSON zurück mit dem Feld 'summary'.",
}


async def get_prompt(db: AsyncSession, category: str) -> dict[str, Any]:
    if category not in DEFAULT_PROMPTS:
        raise LookupError(f"Unknown prompt category. Allowed: {sorted(DEFAULT_PROMPTS)}")
    row = (await db.execute(select(PromptConfig).where(PromptConfig.category == category))).scalar_one_or_none()
    if row:
        return {
            "category": category,
            "prompt_template": row.prompt_template,
            "version": row.version,
            "updated_at": row.updated_at,
            "is_default": False,
        }
    return {
        "category": category,
        "prompt_template": DEFAULT_PROMPTS[category].strip(),
        "version": 0,
        "updated_at": None,
        "is_default": True,
    }


async def current_template(db: AsyncSession, category: str) -> str:
    """The template the AI connector should receive (edited or default)."""
    return (await get_prompt(db, category))["prompt_template"]


async def update_prompt(
    db: AsyncSession, category: str, *, prompt_template: str, change_summary: str | None, actor: str | None
) -> dict[str, Any]:
    if category not in DEFAULT_PROMPTS:
        raise LookupError(f"Unknown prompt category. Allowed: {sorted(DEFAULT_PROMPTS)}")
    if not prompt_template.strip():
        raise ValueError("prompt_template cannot be empty")
    row = (await db.execute(select(PromptConfig).where(PromptConfig.category == category))).scalar_one_or_none()
    if row:
        row.prompt_template = prompt_template
        row.version += 1
    else:
        row = PromptConfig(category=category, prompt_template=prompt_template, version=1)
        db.add(row)
    db.add(
        PromptConfigHistory(
            category=category,
            version=row.version,
            prompt_template=prompt_template,
            change_summary=change_summary,
            created_by=actor,
        )
    )
    await db.flush()
    return await get_prompt(db, category)


async def get_history(db: AsyncSession, category: str, limit: int = 20) -> list[dict[str, Any]]:
    if category not in DEFAULT_PROMPTS:
        raise LookupError(f"Unknown prompt category. Allowed: {sorted(DEFAULT_PROMPTS)}")
    rows = (
        (
            await db.execute(
                select(PromptConfigHistory)
                .where(PromptConfigHistory.category == category)
                .order_by(PromptConfigHistory.version.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "version": h.version,
            "change_summary": h.change_summary,
            "created_by": h.created_by,
            "created_at": h.created_at,
            "prompt_template": h.prompt_template,
        }
        for h in rows
    ]
