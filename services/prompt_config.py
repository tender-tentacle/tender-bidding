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
    "bidding_scarf_enrichment": "Du bist ein neurowissenschaftlicher KI-Analyst für das originale SCARF-Modell (David Rock, 2008). Analysiere Mitarbeiterkommentare streng nach den 5 Dimensionen auf einer Skala von 0.0 bis 100.0: 0-30 = Starke Bedrohung / Frustration / Kritik (Threat; je schlechter das Feedback, desto NIEDRIGER der Score), 40-60 = Neutral, 70-100 = Starke Belohnung / Zufriedenheit (Reward). 1. Status (Wertschätzung 100 vs. Abwertung/Mikromanagement 0), 2. Certainty (Sicherheit 100 vs. Chaos/Unsicherheit 0), 3. Autonomy (Freiraum 100 vs. Zwang/Kontrolle 0), 4. Relatedness (Teamgeist 100 vs. Entlassungen/Silodenken 0), 5. Fairness (Faires Gehalt/Gleichberechtigung 100 vs. Unfair/Vetterliwirtschaft 0). Verwechseln Sie NIEMALS Kritik mit einem hohen Score! Unbewertete Dimensionen auf null setzen.",
    "bidding_news_relevance_sentiment": "Prüfen Sie zwingend, ob der folgende Zeitungsartikel TATSÄCHLICH vom gewerblichen Unternehmen '{company_name}' handelt (z.B. IT-Beratung, Automotive, Industrie) und NICHT von einer gleichnamigen politischen Partei (wie MHP in der Türkei, SPD, CDU), einem allgemeinen Sport-News-Ticker oder völlig artfremden Inhalten. Regeln: is_relevant: true, WENN der Artikel direkt über das Unternehmen berichtet. false, WENN es sich um Politik, Parteien, allgemeine Ticker oder Verwechslung handelt. sentiment_score (0-100): 0-35 (Negativ/Risiko), 36-65 (Neutral), 66-100 (Positiv/Erfolg).",
}


async def get_prompt(db: AsyncSession, category: str) -> dict[str, Any]:
    """Retrieve the current active prompt template for an inference category.

    Queries the prompt configuration table for the given category. If a custom or
    expert-edited template exists, returns it with version and timestamp metadata.
    Otherwise, returns the built-in system default template marked with is_default=True.

    Agent Metadata:
      @intent: Fetch versioned or default AI prompt templates for inference pipelines.
      @domain: Bidding/PromptEngineering
      @capability: config:get_prompt
      @keywords: prompt_config, ai_prompts, template, versioning, defaults
      @side_effects: none (pure query)
      @idempotent: true
      @agent_notes: Raises LookupError if the requested category is not recognized in DEFAULT_PROMPTS.

    Contracts:
      @param db (AsyncSession): Active SQLAlchemy async database session.
      @param category (str): The prompt category key (must exist in DEFAULT_PROMPTS).
      @return (dict[str, Any]): Dictionary with 'category', 'prompt_template', 'version', 'updated_at', and 'is_default'.
      @raises LookupError: If category is unknown.

    Example:
      >>> prompt = await get_prompt(db, "bidding_strategy")
      >>> print(prompt["is_default"])
    """
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
    """Retrieve raw prompt template string for direct transmission to the AI connector.

    Helper function wrapping get_prompt to isolate only the text string template
    required by the AI inference client.

    Agent Metadata:
      @intent: Provide clean string template extraction for AI inference calls.
      @domain: Bidding/PromptEngineering
      @capability: config:current_template
      @keywords: prompt_template, raw_string, ai_connector, inference
      @side_effects: none (pure query)
      @idempotent: true
      @agent_notes: Unpacks 'prompt_template' from get_prompt.

    Contracts:
      @param db (AsyncSession): Database session.
      @param category (str): Known prompt category.
      @return (str): Raw template string.
      @raises LookupError: If category is unrecognized.

    Example:
      >>> tpl = await current_template(db, "bidding_deadlines")
    """
    return (await get_prompt(db, category))["prompt_template"]


async def update_prompt(
    db: AsyncSession, category: str, *, prompt_template: str, change_summary: str | None, actor: str | None
) -> dict[str, Any]:
    """Update a prompt template, bump its version, and record an audit history snapshot.

    Mutates or initializes the active PromptConfig row for a category, increments
    the version counter, creates an immutable PromptConfigHistory snapshot record,
    and flushes changes to the session.

    Agent Metadata:
      @intent: Allow domain experts to adjust AI prompt templates with full versioning and history tracking.
      @domain: Bidding/PromptEngineering
      @capability: config:update_prompt
      @keywords: update_prompt, version_bump, prompt_history, audit, human_override
      @side_effects: db:mutate (upserts PromptConfig, inserts PromptConfigHistory)
      @idempotent: false
      @agent_notes: Flushes the session but does not commit; caller controls transaction completion.

    Contracts:
      @param db (AsyncSession): SQLAlchemy async session.
      @param category (str): Target prompt category key.
      @param prompt_template (str): New prompt template content (non-empty).
      @param change_summary (str | None): Human rationale for the change.
      @param actor (str | None): User identifier of the author.
      @return (dict[str, Any]): Updated prompt metadata dictionary.
      @raises LookupError: If category is unknown.
      @raises ValueError: If prompt_template is blank.

    Example:
      >>> updated = await update_prompt(db, "bidding_deadlines", prompt_template="...", change_summary="Add ISO format rule", actor="expert_1")
    """
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
    """Fetch the versioned revision history for a given prompt category.

    Retrieves up to limit history entries from PromptConfigHistory ordered
    by version descending, revealing who modified the prompt and when.

    Agent Metadata:
      @intent: Audit prompt template evolution across versions for reproducibility and rollbacks.
      @domain: Bidding/PromptEngineering
      @capability: config:get_prompt_history
      @keywords: prompt_history, revisions, versions, audit, changelog
      @side_effects: none (pure query)
      @idempotent: true
      @agent_notes: Orders by version descending; capped at limit records (default 20).

    Contracts:
      @param db (AsyncSession): Database session.
      @param category (str): Prompt category key.
      @param limit (int): Maximum records to retrieve (default 20).
      @return (list[dict[str, Any]]): List of historical version objects with summaries and templates.
      @raises LookupError: If category is unknown.

    Example:
      >>> history = await get_history(db, "bidding_strategy", limit=5)
      >>> print(len(history))
    """
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
