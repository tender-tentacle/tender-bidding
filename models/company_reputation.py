import uuid
from datetime import datetime, timedelta

from core.database import Base
from sqlalchemy import JSON, Column, DateTime, String


class CompanyReputationCache(Base):
    __tablename__ = "company_reputation_cache"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(255), index=True, nullable=False)
    search_type = Column(String(50), nullable=False)  # 'news' or 'jobs'
    cached_data = Column(JSON, nullable=False)
    crawled_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    @property
    def is_valid(self) -> bool:
        """Returns True if cache is less than 30 days old"""
        return datetime.utcnow() - self.crawled_at < timedelta(days=30)
