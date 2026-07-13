import core.ai_client
import core.config
import pytest


@pytest.fixture(autouse=True)
def setup_real_ai(monkeypatch):
    # Set config variables so they are resolved correctly in all imported locations
    monkeypatch.setattr(core.config, "MOCK_MODE", False)
    monkeypatch.setattr(core.config, "AI_URL", "http://localhost:8004")
    monkeypatch.setattr(core.ai_client, "MOCK_MODE", False)
    monkeypatch.setattr(core.ai_client, "AI_URL", "http://localhost:8004")

def test_config_overridden():
    assert core.config.MOCK_MODE is False
    assert core.config.AI_URL == "http://localhost:8004"
    assert core.ai_client.MOCK_MODE is False
    assert core.ai_client.AI_URL == "http://localhost:8004"

@pytest.mark.asyncio
async def test_real_ai_extract_group():
    client = core.ai_client.RealAIClient()
    snapshot = {
        "source_ref": "TEST-real-group-1",
        "source_kind": "group",
        "title": "Digitalisierungsprojekt Schulen und Behörden",
        "customer": "Stadtverwaltung Köln",
        "document_text": """
--- Member 1: IT-Infrastruktur an Schulen ---
Die Stadt Köln schreibt die Beschaffung von Switches, Firewalls und Verkabelungsarbeiten für Schulen aus.
Zum Nachweis der Eignung sind einzureichen:
- Ein aktueller Handelsregisterauszug (nicht älter als 3 Monate ab Angebotsabgabe).
- Mindestens 3 vergleichbare Referenzprojekte über Netzwerktechnik aus den letzten 3 Jahren.

--- Member 2: Softwareplattform für Behörden ---
Entwicklung einer webbasierten Serviceplattform für Bürgerdienste.
Erforderliche Unterlagen:
- Lebensläufe (CVs) des Projektleiters und der beiden Senior-Entwickler mit Zertifizierungsnachweis (ITIL/Scrum).
- Nachweis einer Betriebshaftpflichtversicherung mit Deckungssumme 5 Mio. Euro.
- Eigenerklärung Ausschlussgründe nach § 123 GWB.
- Eigenerklärung Mindestlohn nach MiLoG.
        """,
    }
    docs = await client.extract_required_documents(snapshot)
    assert isinstance(docs, list)
    assert len(docs) > 0
    names = {d["document_name"].lower() for d in docs}

    print("Group extracted docs:", docs)
    # Check if the AI extracted relevant items from the text
    assert any("register" in n or "handelsregister" in n for n in names)
    assert any("referenz" in n for n in names)
    assert any("cv" in n or "lebensl" in n or "projekt" in n for n in names)

@pytest.mark.asyncio
async def test_real_ai_extract_tender():
    client = core.ai_client.RealAIClient()
    snapshot = {
        "source_ref": "TEST-real-tender-1",
        "source_kind": "tender",
        "title": "Rahmenvereinbarung über Cloud-Hosting und Support",
        "customer": "Bundesagentur für Arbeit",
        "document_text": """
Ausschreibung zur Bereitstellung von Cloud-Ressourcen und Support.
Anforderungen an den Bieter:
- Handelsregisterauszug zum Nachweis der Vertretungsberechtigung.
- Eigenerklärung zur Einhaltung des Mindestlohngesetzes.
- Detailliertes Leistungskonzept zur Umsetzung des Projekts.
- Vollständig ausgefülltes Preisblatt im PDF- und GAEB-Format.
        """,
    }
    docs = await client.extract_required_documents(snapshot)
    assert isinstance(docs, list)
    assert len(docs) > 0
    names = {d["document_name"].lower() for d in docs}

    print("Tender extracted docs:", docs)
    assert any("preisblatt" in n or "preis" in n for n in names)
    assert any("konzept" in n or "leistung" in n for n in names)

@pytest.mark.asyncio
async def test_real_ai_extract_lot():
    client = core.ai_client.RealAIClient()
    snapshot = {
        "source_ref": "TEST-real-lot-1",
        "source_kind": "tender",
        "title": "Los 1 - Cloud-Hosting-Infrastruktur",
        "customer": "Bundesagentur für Arbeit",
        "document_text": """
Teillos 1: Hosting der Kernplattform.
Der Bieter muss für dieses Los einreichen:
- ISO 27001 Zertifizierung für das Rechenzentrum.
- Eigenerklärung Ausschlussgründe.
        """,
    }
    docs = await client.extract_required_documents(snapshot)
    assert isinstance(docs, list)
    assert len(docs) > 0
    names = {d["document_name"].lower() for d in docs}

    print("Lot extracted docs:", docs)
    assert any("zertifikat" in n or "zertifizierung" in n or "iso" in n for n in names)
    assert any("ausschluss" in n or "eigenerklärung" in n for n in names)
