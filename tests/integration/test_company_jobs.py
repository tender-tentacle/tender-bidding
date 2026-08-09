from unittest.mock import patch

import httpx
import pytest
from tests.helpers import api_client


@pytest.mark.asyncio
async def test_scrape_company_arbeitsagentur_jobs():
    company_id = "MHP"
    mock_jobsuche_data = [
        {
            "scraped_at": "2026-08-09T10:00:00Z",
            "title": "Senior Cloud Consultant (m/w/d)",
            "location": "71638 Ludwigsburg",
            "hash": "hash_mhp_cloud_123",
            "published_at": "01.08.2026",
            "employment_type": "Vollzeit",
        }
    ]

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, *args, **kwargs):
        if "scrape/jobsuche" in str(url):
            return MockResponse(mock_jobsuche_data)
        return await original_post(self, url, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        async with api_client() as ac:
            # 1. Trigger manual scrape
            scrape_resp = await ac.post(f"/company/{company_id}/jobsuche/scrape")
            assert scrape_resp.status_code == 200
            jobs = scrape_resp.json()
            assert len(jobs) >= 1
            assert jobs[0]["title"] == "Senior Cloud Consultant (m/w/d)"
            assert jobs[0]["location"] == "71638 Ludwigsburg"
            assert jobs[0]["source_url"] == "https://www.arbeitsagentur.de/jobsuche"

            # 2. Get stored Arbeitsagentur jobs
            get_resp = await ac.get(f"/company/{company_id}/jobsuche")
            assert get_resp.status_code == 200
            stored_jobs = get_resp.json()
            assert len(stored_jobs) >= 1
            assert stored_jobs[0]["title"] == "Senior Cloud Consultant (m/w/d)"
            assert stored_jobs[0]["location"] == "71638 Ludwigsburg"
            assert stored_jobs[0]["source_url"] == "https://www.arbeitsagentur.de/jobsuche"


@pytest.mark.asyncio
async def test_get_company_arbeitsagentur_jobs_auto_triggers_scrape_when_uncached():
    company_id = "Flughafen Stuttgart GmbH"
    mock_jobsuche_data = [
        {
            "scraped_at": "2026-08-09T10:00:00Z",
            "title": "Mechatroniker Maschinentechnik",
            "location": "70629 Stuttgart",
            "hash": "hash_flughafen_123",
            "published_at": "08.05.2026",
            "employment_type": "Vollzeit",
        }
    ]

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, *args, **kwargs):
        if "scrape/jobsuche" in str(url):
            return MockResponse(mock_jobsuche_data)
        return await original_post(self, url, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        async with api_client() as ac:
            # GET on uncached company should auto-trigger scrape and return jobs!
            get_resp = await ac.get(f"/company/{company_id}/jobsuche")
            assert get_resp.status_code == 200
            jobs = get_resp.json()
            assert len(jobs) >= 1
            assert jobs[0]["title"] == "Mechatroniker Maschinentechnik"


@pytest.mark.asyncio
async def test_scrape_company_servicebund_jobs():
    company_id = "Landesbetrieb Liegenschafts- und Baubetreuung"
    mock_servicebund_data = [
        {
            "scraped_at": "2026-08-09T10:00:00Z",
            "title": "Ingenieur Elektrotechnik (m/w/d)",
            "location": "Landau in der Pfalz",
            "hash": "hash_servicebund_landesbetrieb_123",
            "published_at": "08.08.2026",
            "employment_type": "Vollzeit oder Teilzeit",
            "source_url": "https://www.service.bund.de/IMPORTE/Stellenangebote/1476821.html",
        }
    ]

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, *args, **kwargs):
        if "servicebund_jobs" in str(url):
            return MockResponse(mock_servicebund_data)
        return await original_post(self, url, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        async with api_client() as ac:
            # 1. Trigger manual scrape
            scrape_resp = await ac.post(f"/company/{company_id}/servicebund_jobs/scrape")
            assert scrape_resp.status_code == 200
            jobs = scrape_resp.json()
            assert len(jobs) >= 1
            assert jobs[0]["title"] == "Ingenieur Elektrotechnik (m/w/d)"
            assert jobs[0]["location"] == "Landau in der Pfalz"
            assert "service.bund.de" in jobs[0]["source_url"]

            # 2. Get stored Bund.de jobs
            get_resp = await ac.get(f"/company/{company_id}/servicebund_jobs")
            assert get_resp.status_code == 200
            stored_jobs = get_resp.json()
            assert len(stored_jobs) >= 1
            assert stored_jobs[0]["title"] == "Ingenieur Elektrotechnik (m/w/d)"
            assert stored_jobs[0]["location"] == "Landau in der Pfalz"
            assert "service.bund.de" in stored_jobs[0]["source_url"]


@pytest.mark.asyncio
async def test_job_endpoint_strict_isolation_and_description_persistence():
    company_id = "Bundesanstalt für Straßen- und Verkehrswesen"
    mock_servicebund_data = [
        {
            "scraped_at": "2026-08-09T10:00:00Z",
            "title": "Wissenschaftliche Mitarbeiterin (m/w/d)",
            "location": "Bergisch Gladbach",
            "hash": "hash_bast_sb_123",
            "published_at": "21.07.2026",
            "employment_type": "Höherer Dienst",
            "description": "Forschung im Bereich Straßenbau und Geotechnik.",
            "source_url": "https://www.service.bund.de/IMPORTE/Stellenangebote/bast/2215252.html",
        }
    ]

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, *args, **kwargs):
        if "servicebund_jobs" in str(url):
            return MockResponse(mock_servicebund_data)
        return await original_post(self, url, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        async with api_client() as ac:
            # 1. Scrape servicebund jobs
            sb_resp = await ac.post(f"/company/{company_id}/servicebund_jobs/scrape")
            assert sb_resp.status_code == 200
            sb_jobs = sb_resp.json()
            assert len(sb_jobs) == 1
            assert sb_jobs[0]["description"] == "Forschung im Bereich Straßenbau und Geotechnik."

            # 2. Query servicebund endpoint -> MUST return the Bund.de job
            sb_get = await ac.get(f"/company/{company_id}/servicebund_jobs")
            assert sb_get.status_code == 200
            assert len(sb_get.json()) == 1
            assert sb_get.json()[0]["description"] == "Forschung im Bereich Straßenbau und Geotechnik."

            # 3. Query jobsuche (Arbeitsagentur) endpoint -> MUST NOT return the Bund.de job
            ba_get = await ac.get(f"/company/{company_id}/jobsuche")
            assert ba_get.status_code == 200
            ba_jobs = ba_get.json()
            assert not any("service.bund.de" in (j.get("source_url") or "") for j in ba_jobs)


@pytest.mark.asyncio
async def test_kununu_jobs_endpoint_filters_out_arbeitsagentur_and_bund_jobs():
    company_id = "Münchner Wohnen GmbH"
    mock_ba_data = [
        {
            "scraped_at": "2026-08-09T10:00:00Z",
            "title": "Sozialpädagog*in (m/w/d)",
            "location": "München",
            "hash": "hash_ba_mw_123",
            "published_at": "2026-06-22",
            "employment_type": "Vollzeit",
            "source_url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/123",
        }
    ]
    mock_kununu_data = [
        {
            "title": "Immobilienkaufmann (m/w/d)",
            "location": "München",
            "hash": "hash_kununu_mw_456",
            "published_at": "2026-07-01",
            "employment_type": "Vollzeit",
            "url": "https://www.kununu.com/de/muenchner-wohnen/jobs/456",
        }
    ]

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    async def mock_post(self, url, *args, **kwargs):
        if "jobsuche" in str(url):
            return MockResponse(mock_ba_data)
        if "kununu/jobs" in str(url):
            return MockResponse(mock_kununu_data)
        return MockResponse([])

    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        async with api_client() as ac:
            # 1. Scrape Arbeitsagentur jobs for company
            ba_resp = await ac.post(f"/company/{company_id}/jobsuche/scrape")
            assert ba_resp.status_code == 200
            assert len(ba_resp.json()) == 1

            # 2. Call GET /company/{company_id}/jobs (Kununu jobs endpoint)
            kununu_resp = await ac.get(f"/company/{company_id}/jobs")
            assert kununu_resp.status_code == 200
            jobs = kununu_resp.json()

            # Assert that Arbeitsagentur jobs are NOT returned in Kununu jobs endpoint
            assert len(jobs) == 1
            assert jobs[0]["title"] == "Immobilienkaufmann (m/w/d)"
            for j in jobs:
                src = (j.get("source_url") or "").lower()
                url_val = (j.get("url") or "").lower()
                assert "arbeitsagentur" not in src and "jobboerse" not in src
                assert "arbeitsagentur" not in url_val and "jobboerse" not in url_val


