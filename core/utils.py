"""Utility helpers for tender bidding service."""

import logging
import re

logger = logging.getLogger("bidding_utils")


def clean_company_name_candidates(name: str) -> list[str]:
    """
    Generates a prioritized list of search query candidates for a company name
    by progressively reducing words from full name down to core brand names:
    e.g. "MHP Management- und IT-Beratung GmbH" ->
    1. "MHP Management- und IT-Beratung GmbH"
    2. "MHP Management- und IT-Beratung"
    3. "MHP Management- IT-Beratung GmbH"
    4. "Management- und IT-Beratung GmbH"
    5. "MHP Management"
    6. "MHP"
    """
    if not name or not name.strip():
        return []

    raw = name.strip()
    candidates: list[str] = []

    def _add(cand: str):
        c = re.sub(r"\s+", " ", cand).strip()
        c = re.sub(r"[\s,\.-]+$", "", c).strip()
        if c and len(c) >= 2 and c not in candidates:
            candidates.append(c)

    # 1. Full original name
    _add(raw)

    # 2. Truncate 'vertreten durch' clauses
    base = re.split(r",?\s+vertreten\s+durch\b", raw, flags=re.IGNORECASE)[0].strip()
    _add(base)

    # 3. Strip legal form extensions
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
    no_legal = re.sub(pattern, "", base, flags=re.IGNORECASE).strip()
    _add(no_legal)

    # 4. Remove filler words (e.g. "und", "&")
    no_fillers = re.sub(r"\b(und|&|des|der|die|das|für|zur)\b", "", raw, flags=re.IGNORECASE).strip()
    _add(no_fillers)
    no_fillers_no_legal = re.sub(pattern, "", no_fillers, flags=re.IGNORECASE).strip()
    _add(no_fillers_no_legal)

    # 5. Left-to-right word reductions (drop first word/brand)
    words = [w for w in re.split(r"\s+", no_legal) if w]
    if len(words) > 1:
        words_no_first = [w for w in re.split(r"\s+", raw) if w][1:]
        if words_no_first:
            _add(" ".join(words_no_first))
        words_no_first_no_legal = [w for w in re.split(r"\s+", no_legal) if w][1:]
        if words_no_first_no_legal:
            _add(" ".join(words_no_first_no_legal))

    # 6. Progressive right-to-left word reductions
    for i in range(len(words) - 1, 0, -1):
        cand_sub = " ".join(words[:i])
        cand_sub = re.sub(r"[\s,\.-]+$", "", cand_sub).strip()
        if cand_sub and not cand_sub.lower().endswith(" und"):
            _add(cand_sub)

    # 7. First word alone if acronym / brand (e.g. "MHP")
    if words:
        first_w = words[0].strip("-,. ")
        _add(first_w)
        if len(first_w) <= 5:
            _add(f"{first_w} Porsche")
            _add(f"{first_w} Beratung")
            _add(f"{first_w} IT")

    return candidates
