from __future__ import annotations

import json
from typing import Any, Dict, Generator, List


def stream_manifest(path: str) -> Generator[Dict[str, Any], None, None]:
    with open(path, "r", encoding="utf-8") as handle:
        first = handle.read(1)
        handle.seek(0)
        if first == "[":
            data = json.load(handle)
            if not isinstance(data, list):
                raise ValueError("manifest JSON must be a list of records")
            for record in data:
                if not isinstance(record, dict):
                    raise ValueError("manifest record must be an object")
                yield record
        else:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("manifest record must be an object")
                yield record


def load_manifest(path: str) -> List[Dict[str, Any]]:
    return list(stream_manifest(path))
