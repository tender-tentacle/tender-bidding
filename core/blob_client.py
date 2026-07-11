"""Blob storage for original bid documents.

Originals live in Azure Blob; markdown + metadata live in the (isolated) SQL DB.
The mock backend writes to a local temp dir so uploads work with no Azure.
"""

from __future__ import annotations

import os
import tempfile
import uuid

from core.config import BLOB_CONTAINER, MOCK_MODE
from core.logger import setup_logger

logger = setup_logger("bidding-blob")


class BlobClient:
    async def upload(self, data: bytes, filename: str) -> str:
        """Store bytes, return a stable blob reference."""
        raise NotImplementedError

    async def download(self, blob_ref: str) -> bytes:
        raise NotImplementedError


class MockBlobClient(BlobClient):
    """Local-temp-dir blob store keyed by a generated blob ref."""

    def __init__(self) -> None:
        self.root = os.path.join(tempfile.gettempdir(), "bidding-blob")
        os.makedirs(self.root, exist_ok=True)

    async def upload(self, data: bytes, filename: str) -> str:
        blob_ref = f"{uuid.uuid4().hex}/{filename}"
        path = os.path.join(self.root, blob_ref)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return blob_ref

    async def download(self, blob_ref: str) -> bytes:
        with open(os.path.join(self.root, blob_ref), "rb") as f:
            return f.read()


class AzureBlobClient(BlobClient):
    """Azure Blob backend. Deferred in v1 — falls back to the mock store."""

    def __init__(self) -> None:
        self._fallback = MockBlobClient()
        logger.warning(f"AzureBlobClient (container '{BLOB_CONTAINER}') not wired in v1; using local store.")

    async def upload(self, data: bytes, filename: str) -> str:
        return await self._fallback.upload(data, filename)

    async def download(self, blob_ref: str) -> bytes:
        return await self._fallback.download(blob_ref)


def get_blob_client() -> BlobClient:
    return MockBlobClient() if MOCK_MODE else AzureBlobClient()
