"""Portal intelligence: competitor/market signals from public procurement portals.

The decision-matrix evaluation asks "who else plays in this space?" — the real
backend queries TED (search API) and bund.de; the mock returns deterministic,
clearly-labelled test data so evaluations are reproducible offline. Same
mock-first pattern as the AI and Blob clients (BIDDING_MOCK).
"""

from __future__ import annotations

from typing import Any

from core.config import MOCK_MODE
from core.logger import setup_logger

logger = setup_logger("portal-intel")

# Deterministic mock market data keyed on CPV prefix (2 digits = CPV division).
_MOCK_MARKET: dict[str, list[dict[str, Any]]] = {
    "72": [  # IT services
        {"name": "Materna SE", "recent_awards": 14, "source": "TED"},
        {"name": "msg systems ag", "recent_awards": 11, "source": "TED"},
        {"name": "Capgemini Deutschland", "recent_awards": 9, "source": "bund.de"},
    ],
    "79": [  # business services / security
        {"name": "Securitas GmbH", "recent_awards": 7, "source": "bund.de"},
        {"name": "WISAG Sicherheit", "recent_awards": 5, "source": "TED"},
    ],
}


class PortalIntelClient:
    """Interface. `competitor_scan` answers: likely competitors + award history."""

    async def competitor_scan(self, customer: str | None, cpv_codes: list[str] | None) -> dict[str, Any]:
        raise NotImplementedError


class MockPortalIntelClient(PortalIntelClient):
    async def competitor_scan(self, customer: str | None, cpv_codes: list[str] | None) -> dict[str, Any]:
        competitors: list[dict[str, Any]] = []
        seen: set[str] = set()
        for code in cpv_codes or []:
            for entry in _MOCK_MARKET.get(code[:2], []):
                if entry["name"] not in seen:
                    seen.add(entry["name"])
                    competitors.append(entry)
        return {
            "customer": customer,
            "cpv_codes": cpv_codes or [],
            "competitors": competitors,
            "source_portals": ["TED", "bund.de"],
            "note": "mock portal data — deterministic, for offline evaluation",
        }


class RealPortalIntelClient(PortalIntelClient):
    """TED search API + bund.de queries. Deferred — falls back to mock data."""

    def __init__(self) -> None:
        self._fallback = MockPortalIntelClient()
        logger.warning("RealPortalIntelClient not wired in v1; using mock market data.")

    async def competitor_scan(self, customer: str | None, cpv_codes: list[str] | None) -> dict[str, Any]:
        return await self._fallback.competitor_scan(customer, cpv_codes)


def get_portal_intel_client() -> PortalIntelClient:
    return MockPortalIntelClient() if MOCK_MODE else RealPortalIntelClient()
