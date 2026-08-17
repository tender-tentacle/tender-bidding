from datetime import UTC, datetime, timedelta


def normalize_news_date(val: str | None) -> str:
    if not val or not str(val).strip():
        return datetime.now(UTC).strftime("%Y-%m-%d")
    s = str(val).strip()
    # Check DD.MM.YYYY
    import re
    m_de = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m_de:
        day, month, year = m_de.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    # Standard ISO string extraction YYYY-MM-DD
    m_iso = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", s)
    if m_iso:
        year, month, day = m_iso.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return s[:10]

def filter_and_sort_news_articles(scraped_articles: list[dict], cutoff_days: int = 730) -> list[dict]:
    cutoff_date = (datetime.now(UTC) - timedelta(days=cutoff_days)).strftime("%Y-%m-%d")
    seen_hashes = set()
    filtered = []

    for item in scraped_articles:
        article_hash = item.get("hash") or item.get("link") or item.get("title")
        if not article_hash or article_hash in seen_hashes:
            continue
        seen_hashes.add(article_hash)

        raw_pub = item.get("published_at") or item.get("published_date") or datetime.now(UTC).strftime("%Y-%m-%d")
        pub_date = normalize_news_date(raw_pub)

        if pub_date >= cutoff_date or len(pub_date) < 10:
            item["_pub_date"] = pub_date
            filtered.append(item)

    filtered.sort(key=lambda x: x.get("_pub_date", ""), reverse=True)
    return filtered


def test_normalize_news_date_german_format():
    assert normalize_news_date("14.02.2025") == "2025-02-14"
    assert normalize_news_date("01.05.2024") == "2024-05-01"

def test_normalize_news_date_iso_and_timestamps():
    assert normalize_news_date("2025-03-10T14:30:00+01:00") == "2025-03-10"
    assert normalize_news_date("2024/11/20") == "2024-11-20"

def test_filter_news_articles_retains_older_and_german_dates():
    scraped = [
        {"title": "German Date News", "link": "https://tagesschau.de/1", "published_at": "14.02.2025"},
        {"title": "Recent ISO News", "link": "https://tagesschau.de/2", "published_at": "2026-08-10"},
        {"title": "Last Year News", "link": "https://tagesschau.de/3", "published_at": "2025-01-15"}
    ]
    result = filter_and_sort_news_articles(scraped, cutoff_days=730)
    assert len(result) == 3
    assert result[0]["title"] == "Recent ISO News"
    assert result[1]["title"] == "German Date News"
    assert result[2]["title"] == "Last Year News"
