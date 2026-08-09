from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.v1.company_profile import get_company_profile


@pytest.mark.asyncio
async def test_company_profile_stores_servicebund_authority_data():
    """Verify get_company_profile fetches and stores servicebund authority details."""
    mock_db = AsyncMock()

    # DB query returns no existing cached profile
    res1 = MagicMock()
    res1.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = res1

    mock_wiki_resp = MagicMock()
    mock_wiki_resp.status_code = 200
    mock_wiki_resp.json.return_value = {
        "description": "GIZ Wikipedia summary",
        "logo_url": "https://upload.wikimedia.org/logo.png",
        "wikipedia_url": "https://de.wikipedia.org/wiki/GIZ",
    }

    mock_servicebund_resp = MagicMock()
    mock_servicebund_resp.status_code = 200
    mock_servicebund_resp.json.return_value = {
        "title": "Deutsche Gesellschaft für Internationale Zusammenarbeit (GIZ) GmbH",
        "description": "GIZ ist ein weltweit tätiges Bundesunternehmen.",
        "main_address": {
            "street": "Friedrich-Ebert-Allee 32 + 36",
            "zipcode": "53113",
            "city": "Bonn",
            "state": "Nordrhein-Westfalen",
            "country": "Deutschland",
        },
        "secondary_address": {
            "street": "Dag-Hammarskjöld-Weg 1 - 5",
            "zipcode": "65760",
            "city": "Eschborn",
            "state": "Hessen",
        },
        "phone": "+49 228 4460-0",
        "fax": "+49 228 4460-1766",
        "email": "info@giz.de",
        "website": "https://www.giz.de",
        "url": "https://www.service.bund.de/Content/DE/DEBehoerden/G/GIZ/GIZ.html",
    }

    async def mock_post(url, **kwargs):
        if "servicebund_authority" in url:
            return mock_servicebund_resp
        return mock_wiki_resp

    with patch("httpx.AsyncClient.post", AsyncMock(side_effect=mock_post)):
        profile = await get_company_profile("GIZ", mock_db)

        assert mock_db.add.call_count == 1
        added_profile = mock_db.add.call_args[0][0]
        assert added_profile.description == "GIZ Wikipedia summary"
        assert added_profile.servicebund_url == "https://www.service.bund.de/Content/DE/DEBehoerden/G/GIZ/GIZ.html"
        assert "Friedrich-Ebert-Allee 32 + 36" in added_profile.servicebund_main_address
        assert added_profile.servicebund_phone == "+49 228 4460-0"
        assert added_profile.servicebund_email == "info@giz.de"
        assert "Dag-Hammarskjöld-Weg" in added_profile.servicebund_secondary_address
