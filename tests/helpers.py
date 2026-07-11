"""In-process ASGI client (no live server), matching the repo's test pattern."""

import httpx
from main import app


def api_client(**kwargs) -> httpx.AsyncClient:
    kwargs.setdefault("transport", httpx.ASGITransport(app=app))
    kwargs.setdefault("base_url", "http://testserver/api/v1")
    return httpx.AsyncClient(**kwargs)


SAMPLE_RELAY = {
    "source_ref": "NID-TEST-1",
    "source_kind": "tender",
    "title": "Cloud Platform Services",
    "customer": "Stadt Musterstadt",
    "source_system": "Öffentliche Vergabe",
    "driver_user_id": "u-driver",
    "deadline_at": "2099-09-01T12:00:00Z",
    "questions_deadline_at": "2099-08-15T12:00:00Z",
    "document_text": "Bau und Betrieb einer Cloud-Plattform. Bietergemeinschaft möglich.",
    "lots": [
        {"lot_id": "LOT-0001", "lot_number": 1, "title": "Los 1", "document_text": "Netzwerk"},
        {"lot_id": "LOT-0002", "lot_number": 2, "title": "Los 2", "document_text": "Storage"},
    ],
}
