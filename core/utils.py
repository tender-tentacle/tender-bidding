"""Utility helpers for tender bidding service."""

import logging
import re

logger = logging.getLogger("bidding_utils")


def clean_company_name_candidates(name: str) -> list[str]:
    """Generate search query candidates for company lookups by progressive right-to-left reduction.

    Generates search query candidates by progressively removing the LAST word
    from the right, assuming the most important brand words are at the FRONT.
    Strips German and international legal forms, representation clauses ('vertreten durch'),
    trailing conjunctions/prepositions, and punctuation.

    Agent Metadata:
      @intent: Produce high-recall query variations for company intelligence crawlers (Northdata, Handelsregister).
      @domain: Bidding/Core
      @capability: util:clean_company_name
      @keywords: company_name, query_candidates, legal_forms, normalization, entity_resolution
      @side_effects: none (pure)
      @idempotent: true
      @agent_notes: Filters out candidates that are purely legal form identifiers.

    Contracts:
      @param name (str): Raw company name string (e.g. from tender buyer or contractor field).
      @return (list[str]): Deduplicated list of search candidate strings ordered from specific to general.
      @raises None: Pure function.

    Example:
      >>> candidates = clean_company_name_candidates("MHP Management- und IT-Beratung GmbH")
      >>> "MHP" in candidates
      True
    """
    if not name or not name.strip():
        return []

    raw = name.strip()
    candidates: list[str] = []

    legal_forms = [
        r"Gesellschaft\s+mit\s+beschränkter\s+Haftung",
        r"Anstalt\s+des\s+öffentlichen\s+Rechts",
        r"Körperschaft\s+des\s+öffentlichen\s+Rechts",
        r"Stiftung\s+des\s+öffentlichen\s+Rechts",
        r"Aktiengesellschaft",
        r"Kommanditgesellschaft",
        r"GmbH\s*&\s*Co\.?\s*KG",
        r"GmbH\s*&\s*Co\.?",
        r"GmbH",
        r"mbH",
        r"AG",
        r"SE",
        r"KG",
        r"e\.?\s*V\.?",
        r"AöR",
        r"KdöR",
        r"KöR",
        r"Ltd\.?",
        r"Inc\.?",
        r"Corp\.?",
        r"Co\.?",
    ]
    pattern_legal = r"\b(" + "|".join(legal_forms) + r")\b"
    pattern_exact_legal = r"^(" + "|".join(legal_forms) + r")$"

    def _add(cand: str) -> None:
        """Sanitize and record a company candidate string if distinct and non-legal.

        Agent Metadata:
          @intent: Clean whitespace, trailing noise words, and append valid search candidate tokens.
          @domain: Bidding/Core
          @capability: util:normalize_token
          @keywords: sanitize, regex, token_clean
          @side_effects: none (mutates local candidates list)
          @idempotent: false
          @agent_notes: Ignores candidates with length < 2 or pure legal form names.

        Contracts:
          @param cand (str): Candidate string.
          @return None: Appends in-place to candidates list.
          @raises None: Pure helper closure.

        Example:
          >>> _add("MHP Management")
        """
        c = re.sub(r"\s+", " ", cand).strip()
        c = re.sub(r"[\s,\.-]+$", "", c).strip()
        c = re.sub(r"^\s*[\(\[\{]\s*", "", c).strip()
        c = re.sub(r"\s*[\)\]\}]\s*$", "", c).strip()
        c = re.sub(
            r"\b(und|&|des|der|die|das|für|zur|von|mit|in|on|at|of|for)\b$",
            "",
            c,
            flags=re.IGNORECASE,
        ).strip()
        c = re.sub(r"[\s,\.-]+$", "", c).strip()

        if c and len(c) >= 2 and c not in candidates:
            if not re.match(pattern_exact_legal, c, flags=re.IGNORECASE):
                candidates.append(c)

    # 1. Full original name
    _add(raw)

    # 2. Representation clause truncation
    base = re.split(r",?\s+vertreten\s+durch\b", raw, flags=re.IGNORECASE)[0].strip()
    _add(base)

    # 3. Legal form stripped
    no_legal = re.sub(pattern_legal, "", base, flags=re.IGNORECASE).strip()
    _add(no_legal)

    # 4. Tokenize by splitting on whitespace & hyphens
    tokens = [w.strip(".,()[]{}-") for w in re.split(r"[\s-]+", no_legal) if w.strip(".,()[]{}-")]

    # 5. Progressively remove the LAST word from right to left
    for i in range(len(tokens), 0, -1):
        sub_phrase = " ".join(tokens[:i])
        _add(sub_phrase)

    return candidates
