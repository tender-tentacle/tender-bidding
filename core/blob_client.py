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
    """Abstract interface defining the contract for binary document storage."""

    async def upload(self, data: bytes, filename: str) -> str:
        """Store raw document bytes and return a stable retrieval blob reference.

        Agent Metadata:
          @intent: Persist binary file data to object storage and obtain a unique reference URI.
          @domain: Bidding/Infrastructure
          @capability: blob:upload
          @keywords: blob_storage, upload, binary_data, document_store
          @side_effects: file:write
          @idempotent: false
          @agent_notes: Generates a unique reference path for every upload.

        Contracts:
          @param data (bytes): Raw binary payload of the document.
          @param filename (str): Original filename for metadata and pathing.
          @return (str): Stable blob reference path or URI.
          @raises NotImplementedError: In interface definition.

        Example:
          >>> ref = await client.upload(content_bytes, "annex_a.pdf")
        """
        raise NotImplementedError

    async def download(self, blob_ref: str) -> bytes:
        """Retrieve raw document bytes from storage given a stable blob reference.

        Agent Metadata:
          @intent: Read back stored binary document contents for parsing or user downloads.
          @domain: Bidding/Infrastructure
          @capability: blob:download
          @keywords: blob_storage, download, binary_data, read_document
          @side_effects: none (pure read)
          @idempotent: true
          @agent_notes: Must match reference returned by upload.

        Contracts:
          @param blob_ref (str): Relative or absolute storage identifier.
          @return (bytes): Complete binary file payload.
          @raises NotImplementedError: In interface definition.
          @raises FileNotFoundError: If blob reference does not exist.

        Example:
          >>> data = await client.download(ref)
        """
        raise NotImplementedError


class MockBlobClient(BlobClient):
    """Local-temp-dir blob store keyed by a generated blob ref."""

    def __init__(self) -> None:
        """Initialize mock filesystem storage directory inside OS temporary directory.

        Agent Metadata:
          @intent: Set up mock local storage folder for test runs without Azure credentials.
          @domain: Bidding/Infrastructure
          @capability: blob:init_mock
          @keywords: mock_storage, tempdir, local_filesystem
          @side_effects: file:write (creates directory)
          @idempotent: true
          @agent_notes: Initializes root directory under tempfile.gettempdir()/bidding-blob.

        Contracts:
          @return None
          @raises OSError: If temp directory creation fails.

        Example:
          >>> client = MockBlobClient()
        """
        self.root = os.path.join(tempfile.gettempdir(), "bidding-blob")
        os.makedirs(self.root, exist_ok=True)

    async def upload(self, data: bytes, filename: str) -> str:
        """Write binary file to local temp directory using a UUID subpath.

        Agent Metadata:
          @intent: Store file contents locally during offline or mock testing.
          @domain: Bidding/Infrastructure
          @capability: blob:upload_local
          @keywords: local_upload, temp_file, uuid_key
          @side_effects: file:write
          @idempotent: false
          @agent_notes: Creates parent folder on demand.

        Contracts:
          @param data (bytes): Raw binary data.
          @param filename (str): Target filename.
          @return (str): Relative blob reference string 'UUID/filename'.
          @raises OSError: If filesystem write fails.

        Example:
          >>> ref = await mock_client.upload(b"content", "doc.pdf")
        """
        blob_ref = f"{uuid.uuid4().hex}/{filename}"
        path = os.path.join(self.root, blob_ref)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return blob_ref

    async def download(self, blob_ref: str) -> bytes:
        """Read binary contents of a file from the local mock directory.

        Agent Metadata:
          @intent: Load stored file bytes from the mock temp filesystem.
          @domain: Bidding/Infrastructure
          @capability: blob:download_local
          @keywords: local_download, read_bytes, temp_file
          @side_effects: none (pure read)
          @idempotent: true
          @agent_notes: Resolves path relative to self.root.

        Contracts:
          @param blob_ref (str): Relative blob reference.
          @return (bytes): Raw bytes.
          @raises FileNotFoundError: If path does not exist on disk.

        Example:
          >>> data = await mock_client.download("abc/doc.pdf")
        """
        with open(os.path.join(self.root, blob_ref), "rb") as f:
            return f.read()


class AzureBlobClient(BlobClient):
    """Azure Blob backend. Deferred in v1 — falls back to the mock store."""

    def __init__(self) -> None:
        """Initialize Azure Blob client adapter with local mock fallback for v1.

        Agent Metadata:
          @intent: Provide Azure Blob storage client interface with seamless v1 mock fallback.
          @domain: Bidding/Infrastructure
          @capability: blob:init_azure
          @keywords: azure_blob, cloud_storage, fallback
          @side_effects: none
          @idempotent: true
          @agent_notes: Falls back to MockBlobClient in v1.

        Contracts:
          @return None

        Example:
          >>> client = AzureBlobClient()
        """
        self._fallback = MockBlobClient()
        logger.warning(f"AzureBlobClient (container '{BLOB_CONTAINER}') not wired in v1; using local store.")

    async def upload(self, data: bytes, filename: str) -> str:
        """Delegate upload to internal storage backend.

        Agent Metadata:
          @intent: Upload binary payload to object storage.
          @domain: Bidding/Infrastructure
          @capability: blob:upload_azure
          @keywords: azure_upload, delegate
          @side_effects: file:write
          @idempotent: false
          @agent_notes: Forwards to mock fallback in v1.

        Contracts:
          @param data (bytes): File bytes.
          @param filename (str): Filename.
          @return (str): Blob reference.
          @raises OSError: If write fails.

        Example:
          >>> ref = await client.upload(b"data", "test.txt")
        """
        return await self._fallback.upload(data, filename)

    async def download(self, blob_ref: str) -> bytes:
        """Delegate download to internal storage backend.

        Agent Metadata:
          @intent: Fetch file bytes from object storage.
          @domain: Bidding/Infrastructure
          @capability: blob:download_azure
          @keywords: azure_download, delegate
          @side_effects: none (pure read)
          @idempotent: true
          @agent_notes: Forwards to mock fallback in v1.

        Contracts:
          @param blob_ref (str): Blob reference.
          @return (bytes): File bytes.
          @raises FileNotFoundError: If reference not found.

        Example:
          >>> data = await client.download(ref)
        """
        return await self._fallback.download(blob_ref)


def get_blob_client() -> BlobClient:
    """Factory function returning the configured BlobClient implementation.

    Agent Metadata:
      @intent: Supply dependency-injected blob storage client according to MOCK_MODE configuration.
      @domain: Bidding/Infrastructure
      @capability: blob:get_client
      @keywords: factory, blob_client, mock_mode, dependency_injection
      @side_effects: none
      @idempotent: true
      @agent_notes: Returns MockBlobClient when MOCK_MODE is true, otherwise AzureBlobClient.

    Contracts:
      @return (BlobClient): Instantiated storage client implementing BlobClient.
      @raises None: Pure factory.

    Example:
      >>> client = get_blob_client()
    """
    return MockBlobClient() if MOCK_MODE else AzureBlobClient()
