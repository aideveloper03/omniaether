from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import mimetypes
import os
from typing import Any, Dict, Generator
from uuid import uuid4

from storage.hashing import compute_content_hash


class LocalFileMiner:
    def __init__(
        self,
        root_path: str,
        batch_id: str,
        source_provenance: str = "local_file",
        preview_bytes: int = 4096,
    ) -> None:
        self.root_path = root_path
        self.batch_id = batch_id
        self.source_provenance = source_provenance
        self.preview_bytes = preview_bytes

    def iter_records(self) -> Generator[Dict[str, Any], None, None]:
        for root, _, files in os.walk(self.root_path):
            for name in files:
                path = os.path.join(root, name)
                try:
                    size = os.path.getsize(path)
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                content_type, _ = mimetypes.guess_type(path)
                content_type = content_type or "application/octet-stream"
                file_hash = self._hash_file(path)
                payload = {
                    "file_path": path,
                    "file_name": name,
                    "size_bytes": size,
                    "file_sha256": file_hash,
                    "content_preview": self._preview_text(path),
                }
                metadata = {
                    "extension": os.path.splitext(name)[1].lstrip("."),
                    "modified_ts": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
                }
                content_hash = compute_content_hash(
                    payload, metadata, content_type, self.source_provenance
                )
                yield {
                    "primary_key": file_hash,
                    "batch_id": self.batch_id,
                    "source_provenance": self.source_provenance,
                    "timestamp": datetime.fromtimestamp(mtime, timezone.utc),
                    "content_hash": content_hash,
                    "content_type": content_type,
                    "payload": payload,
                    "metadata": metadata,
                    "telemetry": {
                        "trace_id": str(uuid4()),
                        "proxy_id": "local",
                        "user_agent": "local-file-miner",
                        "latency_ms": 0,
                        "success_rate": 1.0,
                    },
                }

    @staticmethod
    def _hash_file(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _preview_text(self, path: str) -> str:
        try:
            with open(path, "rb") as handle:
                content = handle.read(self.preview_bytes)
            return content.decode("utf-8", errors="replace")
        except OSError:
            return ""
