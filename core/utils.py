"""Utility helpers for tender bidding service."""

import logging
import re

logger = logging.getLogger("bidding_utils")


def clean_company_name_candidates(name: str) -> list[str]:
    """
    Generates a prioritized list of search query candidates for a company name
    ordered strictly from longest full name down to progressively reduced terms:
    e.g. "MHP Management- und IT-Beratung GmbH" ->
    1. "MHP Management- und IT-Beratung GmbH" (36 chars)
    2. "MHP Management- und IT-Beratung" (31 chars)
    3. "MHP Management und IT Beratung" (30 chars)
    4. "MHP Management- IT-Beratung" (27 chars)
    5. "MHP Management und IT" (21 chars)
    6. "MHP Management" (14 chars)
    7. "MHP" (3 chars)

    The caller queries Tagesschau with each candidate in sequence and STOPS
    as soon as news articles are found for a candidate.
    """
    if not name or not name.strip():
        return []

    raw = name.strip()
    raw_candidates: list[str] = []

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

    def _add(cand: str):
        c = re.sub(r"\s+", " ", cand).strip()
        c = re.sub(r"[\s,\.-]+$", "", c).strip()
        c = re.sub(r"^\s*[\(\[\{]\s*", "", c).strip()
        c = re.sub(r"\s*[\)\]\}]\s*$", "", c).strip()
        if c and len(c) >= 2 and c not in raw_candidates:
            if not re.match(pattern_exact_legal, c, flags=re.IGNORECASE):
                raw_candidates.append(c)

    # 1. Full raw name
    _add(raw)

    # 2. Truncate 'vertreten durch' clauses
    base = re.split(r",?\s+vertreten\s+durch\b", raw, flags=re.IGNORECASE)[0].strip()
    _add(base)

    # 3. Strip legal form extensions
    no_legal = re.sub(pattern_legal, "", base, flags=re.IGNORECASE).strip()
    _add(no_legal)

    # 4. Remove filler words / prepositions
    no_fillers = re.sub(
        r"\b(und|&|des|der|die|das|für|zur|von|mit|in|on|at|of|for)\b",
        "",
        no_legal,
        flags=re.IGNORECASE,
    ).strip()
    _add(no_fillers)

    # 5. Extract word tokens splitting on whitespace & hyphens
    words = [w.strip(".,()[]{}-") for w in re.split(r"[\s-]+", no_legal) if w.strip(".,()[]{}-")]
    first_token = words[0] if words else ""

    # 6. Progressive right-to-left word reductions
    for i in range(len(words), 0, -1):
        phrase = " ".join(words[:i])
        phrase_clean = re.sub(
            r"\b(und|&|des|der|die|das|für|zur|von|mit|in|on|at|of|for)\b$",
            "",
            phrase,
            flags=re.IGNORECASE,
        ).strip()
        _add(phrase_clean)

    # 7. Progressive left-to-right word reductions
    raw_words = [w.strip(".,()[]{}-") for w in re.split(r"[\s-]+", raw) if w.strip(".,()[]{}-")]
    if len(raw_words) > 1:
        for i in range(1, len(raw_words)):
            phrase = " ".join(raw_words[i:])
            phrase_no_legal = re.sub(pattern_legal, "", phrase, flags=re.IGNORECASE).strip()
            _add(phrase)
            _add(phrase_no_legal)

    # Separate candidates: primary (containing brand token) vs secondary
    primary = []
    secondary = []

    for c in raw_candidates:
        if first_token and first_token.lower() in c.lower():
            primary.append(c)
        else:
            secondary.append(c)

    primary.sort(key=lambda s: len(s), reverse=True)
    secondary.sort(key=lambda s: len(s), reverse=True)

    final_candidates = []
    for c in primary + secondary:
        if c not in final_candidates:
            final_candidates.append(c)

    return final_candidates
