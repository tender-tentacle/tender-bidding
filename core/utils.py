"""Utility helpers for tender bidding service."""

import logging
import re

logger = logging.getLogger("bidding_utils")


def clean_company_name_candidates(name: str) -> list[str]:
    """
    Generates a prioritized list of search query candidates for a company name
    by stripping legal form extensions (GmbH, AG, SE, KG, GmbH & Co. KG, e.V., etc.),
    authority representation clauses ('vertreten durch...'), and prepositional suffixes.
    """
    if not name or not name.strip():
        return []

    raw = name.strip()

    # 1. Truncate 'vertreten durch' clauses
    base = re.split(r",?\s+vertreten\s+durch\b", raw, flags=re.IGNORECASE)[0].strip()

    # 2. Legal form suffixes (ordered long to short)
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
    pattern = r"\b(" + "|".join(legal_forms) + r")\b"
    cleaned = re.sub(pattern, "", base, flags=re.IGNORECASE).strip()

    # 3. Clean leading/trailing punctuation, brackets, parentheses, extra spaces
    cleaned = re.sub(r"[\s,\.-]+$", "", cleaned).strip()
    cleaned = re.sub(r"^\s*[\(\[\{]\s*", "", cleaned)
    cleaned = re.sub(r"\s*[\)\]\}]\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    candidates = []
    if cleaned and len(cleaned) >= 2:
        candidates.append(cleaned)

        # Sub-candidate: split on prepositions if phrase is long
        sub = re.split(r"\s+(?:zur|für|of|for)\s+", cleaned, flags=re.IGNORECASE)[0].strip()
        if sub and sub not in candidates and len(sub) >= 2:
            candidates.append(sub)
            sub_nohyphen = re.sub(
                r"-(?:Gesellschaft|Stiftung|Konzern|Gruppe|Holding)$", "", sub, flags=re.IGNORECASE
            ).strip()
            if sub_nohyphen and sub_nohyphen not in candidates and len(sub_nohyphen) >= 2:
                candidates.append(sub_nohyphen)

    if base and base not in candidates and len(base) >= 2:
        candidates.append(base)
    if raw not in candidates:
        candidates.append(raw)

    return candidates
