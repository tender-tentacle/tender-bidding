"""Runtime configuration for the bidding service.

The service is designed to run fully MOCKED on test data: with BIDDING_MOCK
unset/true it uses in-memory AI + local-temp blob backends and a local SQLite
DB, so it boots and the UI renders with no live enriching / ai-connector /
Azure Blob / Azure SQL dependency.
"""

import os


def _truthy(val: str | None, default: bool) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Mock mode is ON by default — v1 ships as a self-contained, demoable service.
MOCK_MODE: bool = _truthy(os.getenv("BIDDING_MOCK"), default=True)

# Own, ISOLATED database (separate Azure SQL server in prod). Local dev/tests
# fall back to SQLite so nothing external is required.
DATABASE_URL: str = os.getenv("DATABASE_URL") or ""

# Azure Blob for original documents (mock backend writes to a temp dir).
BLOB_CONNECTION_STRING: str = os.getenv("BIDDING_BLOB_CONNECTION_STRING", "")
BLOB_CONTAINER: str = os.getenv("BIDDING_BLOB_CONTAINER", "bid-documents")

# ai-connector base URL (unused in mock mode).
AI_URL: str = os.getenv("AI_URL", "http://ai:8004")

# tender-enriching base URL
ENRICHING_URL: str = os.getenv("ENRICHING_URL", "http://enriching:8002")

ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:8009")
