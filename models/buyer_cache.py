import uuid
from datetime import UTC, datetime

from core.database import Base
from sqlalchemy import JSON, Column, DateTime, String


def generate_uuid():
    return str(uuid.uuid4())


class BuyerIntelligenceCacheORM(Base):
    __tablename__ = "buyer_intelligence_cache"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_id = Column(String(255), nullable=False, index=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    historical_pricing_payload = Column(JSON, nullable=False)
