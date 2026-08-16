"""Utility helpers for tender bidding service."""

import logging
import re

logger = logging.getLogger("bidding_utils")


def clean_company_name_candidates(name: str) -> list[str]:
    """
    Generates search query candidates by progressively removing the LAST word
    from the right, assuming the most important brand words are at the FRONT.

    e.g. "MHP Management- und IT-Beratung GmbH" ->
    1. "MHP Management- und IT-Beratung GmbH" (Full raw name)
    2. "MHP Management- und IT-Beratung" (Drop "GmbH")
    3. "MHP Management und IT Beratung" (Normalized hyphens)
    4. "MHP Management und IT" (Drop "Beratung")
    5. "MHP Management" (Drop "IT" and "und")
    6. "MHP" (Drop "Management")
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

    def _add(cand: str):
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
