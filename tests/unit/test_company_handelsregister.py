from datetime import UTC, datetime

import pytest
from core.database import SessionLocal
from models.bid import CompanyHandelsregister
from sqlalchemy import select


@pytest.mark.asyncio
async def test_company_handelsregister_persistence_and_fields():
    async with SessionLocal() as db_session:
        # 1. Create a CompanyHandelsregister record with Aktueller Abdruck (AD) documents
        data = CompanyHandelsregister(
            company_id="MHP Management- und IT-Beratung GmbH",
            source="handelsregister.de",
            query="MHP Management- und IT-Beratung GmbH",
            documents=[
                {
                    "type": "AD",
                    "title": "Aktueller Abdruck (AD)",
                    "original_pdf_url": "https://www.handelsregister.de/rp_web/search.do?q=MHP%20Management-%20und%20IT-Beratung%20GmbH",
                    "markdown": "# 📜 Handelsregister - Aktueller Abdruck (AD) - MHP Management- und IT-Beratung GmbH\n\n> 📄 **Original-Dokument:** [Handelsregister.de Suche öffnen](https://www.handelsregister.de/rp_web/search.do?q=MHP%20Management-%20und%20IT-Beratung%20GmbH)\n\n## 🏢 Official Corporate Identity\n- **Firma / Legal Name:** MHP Management- und IT-Beratung GmbH\n- **Rechtsform / Legal Form:** GmbH\n- **Registergericht / Court:** Amtsgericht Stuttgart\n- **Registernummer:** HRB 205571\n- **Sitz / Registered Seat:** Ludwigsburg\n- **Status:** Aktuell\n\n## 💰 Capital & Financials\n- **Stammkapital / Grundkapital:** k.A.\n- **Währung:** EUR\n\n## 👥 Governance & Representatives\n- **Vertretungsregelung:** Ist nur ein Geschäftsführer bestellt, so vertritt er die Gesellschaft allein. Sind mehrere Geschäftsführer bestellt, wird die Gesellschaft durch zwei Geschäftsführer gemeinsam vertreten.\n## 📝 Auszug aus dem Registerinhalt\n```text\nHandelsregister Bekanntmachung - Aktueller Abdruck (AD)\nAmtsgericht: Amtsgericht Stuttgart\nRegisternummer: HRB 205571\nFirma: MHP Management- und IT-Beratung GmbH\nSitz: Ludwigsburg\nRechtsform: GmbH\nGeschäftsführung: Ralf Hofmann, Marc de la Bastide\nVertretungsregelung: Ist nur ein Geschäftsführer bestellt, so vertritt er die Gesellschaft allein. Sind mehrere Geschäftsführer bestellt, wird die Gesellschaft durch zwei Geschäftsführer gemeinsam vertreten.\n```"
                }
            ],
            crawled_date=datetime.now(UTC),
        )

        db_session.add(data)
        await db_session.commit()

        # 2. Fetch and assert Handelsregister data is persisted in Bidding DB
        res = await db_session.execute(
            select(CompanyHandelsregister).where(CompanyHandelsregister.company_id == "MHP Management- und IT-Beratung GmbH")
        )
        saved = res.scalars().first()

        assert saved is not None
        assert saved.source == "handelsregister.de"
        assert saved.query == "MHP Management- und IT-Beratung GmbH"
        assert len(saved.documents) == 1
        assert saved.documents[0]["type"] == "AD"
        assert "HRB 205571" in saved.documents[0]["markdown"]
        assert "Amtsgericht Stuttgart" in saved.documents[0]["markdown"]
        assert "Ralf Hofmann, Marc de la Bastide" in saved.documents[0]["markdown"]
