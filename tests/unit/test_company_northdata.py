from datetime import UTC, datetime

import pytest
from core.database import SessionLocal
from models.bid import CompanyNorthData
from sqlalchemy import select


@pytest.mark.asyncio
async def test_company_northdata_persistence_and_fields():
    async with SessionLocal() as db_session:
        # 1. Create a CompanyNorthData record with full parsed fields
        data = CompanyNorthData(
            company_id="MHP Management- und IT-Beratung GmbH",
            company_name="MHP Management- und IT-Beratung GmbH",
            address="Königsallee 49, D-71638 Ludwigsburg",
            founding_date="1996",
            register_court="Amtsgericht Stuttgart",
            register_number="HRB 205571",
            euid="DEB8534.HRB205571",
            lei_code="3912001F4V339T0Z9469",
            business_purpose="Management-Beratung & IT-Dienstleistungen",
            former_names=["Mieschke, Hofmann und Partner GmbH"],
            officers=[{"name": "Federico Magno", "role": "Geschäftsführer"}],
            events=[{"date": "2024-01-01", "summary": "Eintragung im Handelsregister"}],
            balance_sheet={"total_assets": "552,6 Mio. €", "date": "31.12.2024"},
            financials=[{"year": "2024", "revenue": "810,4 Mio. €", "profit": "98,4 Mio. €"}],
            ownership=[{"shareholder": "Dr. Ing. h.c. F. Porsche AG", "share": "100%"}],
            source_url="https://www.northdata.de/MHP",
            crawled_date=datetime.now(UTC),
        )

        db_session.add(data)
        await db_session.commit()

        # 2. Fetch and assert all fields are persisted cleanly
        res = await db_session.execute(
            select(CompanyNorthData).where(CompanyNorthData.company_id == "MHP Management- und IT-Beratung GmbH")
        )
        saved = res.scalars().first()

        assert saved is not None
        assert saved.register_court == "Amtsgericht Stuttgart"
        assert saved.register_number == "HRB 205571"
        assert saved.euid == "DEB8534.HRB205571"
        assert saved.lei_code == "3912001F4V339T0Z9469"
        assert saved.balance_sheet["total_assets"] == "552,6 Mio. €"
        assert saved.financials[0]["revenue"] == "810,4 Mio. €"
        assert saved.ownership[0]["shareholder"] == "Dr. Ing. h.c. F. Porsche AG"
        assert saved.officers[0]["name"] == "Federico Magno"
