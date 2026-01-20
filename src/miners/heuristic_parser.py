from __future__ import annotations

import re
from typing import Dict, List


class LiteParser:
    def __init__(self) -> None:
        self._risk_keywords = [
            "litigation",
            "lawsuit",
            "penalty",
            "compliance",
            "regulatory",
            "sanction",
            "breach",
            "investigation",
            "fraud",
            "restatement",
        ]
        self._asset_keywords = [
            "server",
            "database",
            "kubernetes",
            "aws",
            "azure",
            "gcp",
            "vpn",
            "endpoint",
            "employee",
            "api",
            "crm",
        ]

    def classify(self, text: str) -> Dict[str, List[Dict[str, str]]]:
        return {
            "entity_graph": self._extract_entities(text),
            "risk_vectors": self._extract_risks(text),
            "asset_inventory": self._extract_assets(text),
        }

    def _extract_entities(self, text: str) -> List[Dict[str, str]]:
        relations: List[Dict[str, str]] = []
        patterns = [
            re.compile(r"(?P<child>[A-Z][A-Za-z0-9&\-\s]+)\s+subsidiary of\s+(?P<parent>[A-Z][A-Za-z0-9&\-\s]+)", re.I),
            re.compile(r"(?P<parent>[A-Z][A-Za-z0-9&\-\s]+)\s+acquired\s+(?P<child>[A-Z][A-Za-z0-9&\-\s]+)", re.I),
        ]
        for pattern in patterns:
            for match in pattern.finditer(text):
                relations.append(
                    {
                        "parent": match.group("parent").strip(),
                        "child": match.group("child").strip(),
                        "relation": "ownership",
                    }
                )
        return relations

    def _extract_risks(self, text: str) -> List[Dict[str, str]]:
        risks: List[Dict[str, str]] = []
        lower = text.lower()
        for keyword in self._risk_keywords:
            if keyword in lower:
                risks.append(
                    {
                        "keyword": keyword,
                        "snippet": self._snippet(text, keyword),
                    }
                )
        return risks

    def _extract_assets(self, text: str) -> List[Dict[str, str]]:
        assets: List[Dict[str, str]] = []
        lower = text.lower()
        for keyword in self._asset_keywords:
            if keyword in lower:
                assets.append({"asset": keyword, "snippet": self._snippet(text, keyword)})
        return assets

    @staticmethod
    def _snippet(text: str, keyword: str, window: int = 80) -> str:
        index = text.lower().find(keyword)
        if index == -1:
            return ""
        start = max(index - window, 0)
        end = min(index + window, len(text))
        return text[start:end].replace("\n", " ").strip()
