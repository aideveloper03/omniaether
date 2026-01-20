from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Dict


def canonical_json(data: Any) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def compute_content_hash(
    payload: Dict[str, Any],
    metadata: Dict[str, Any],
    content_type: str,
    source_provenance: str,
) -> str:
    digest = sha256()
    digest.update(canonical_json(payload))
    digest.update(canonical_json(metadata))
    digest.update(content_type.encode("utf-8"))
    digest.update(source_provenance.encode("utf-8"))
    return digest.hexdigest()


def verify_content_hash(
    content_hash: str,
    payload: Dict[str, Any],
    metadata: Dict[str, Any],
    content_type: str,
    source_provenance: str,
) -> bool:
    expected = compute_content_hash(payload, metadata, content_type, source_provenance)
    return content_hash == expected
