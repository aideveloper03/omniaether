"""Automated Intelligence Transformation for AETHER-MINE.

Integrates LLM-Lite Parser (Ollama/OpenAI) to categorize unstructured data:
- Entity_Graph: Relationships between entities found in documents
- Risk_Vectors: Financial anomalies or legal red flags
- Asset_Inventory: Technologies, employees, servers discovered via metadata
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from enum import Enum

import httpx
import structlog

from src.core.config import get_settings
from src.core.models import IntelligenceCategory, MinedRecord


logger = structlog.get_logger(__name__)


class EntityType(str, Enum):
    """Types of entities that can be extracted."""
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    FINANCIAL = "financial"
    TECHNOLOGY = "technology"
    LEGAL = "legal"
    DATE = "date"
    MONEY = "money"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    IP_ADDRESS = "ip_address"


@dataclass
class ExtractedEntity:
    """An entity extracted from content."""
    
    entity_type: EntityType
    value: str
    confidence: float
    context: str
    start_pos: int = 0
    end_pos: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityRelationship:
    """A relationship between two entities."""
    
    source_entity: ExtractedEntity
    target_entity: ExtractedEntity
    relationship_type: str
    confidence: float
    evidence: str


@dataclass
class RiskVector:
    """An identified risk or anomaly."""
    
    risk_type: str
    severity: Literal["low", "medium", "high", "critical"]
    description: str
    evidence: list[str]
    confidence: float
    recommendations: list[str] = field(default_factory=list)


@dataclass
class AssetInventoryItem:
    """A discovered asset (technology, server, etc.)."""
    
    asset_type: str
    name: str
    version: str | None
    details: dict[str, Any]
    source: str
    confidence: float


@dataclass
class IntelligenceReport:
    """Complete intelligence analysis report."""
    
    record_id: str
    source_url: str
    analyzed_at: datetime
    category: IntelligenceCategory
    entities: list[ExtractedEntity]
    relationships: list[EntityRelationship]
    risk_vectors: list[RiskVector]
    asset_inventory: list[AssetInventoryItem]
    summary: str
    raw_llm_response: str | None = None


class LLMProvider:
    """Base class for LLM providers."""
    
    async def complete(self, prompt: str) -> str:
        """Generate completion for prompt."""
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    """Ollama LLM provider for local inference."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
    
    async def complete(self, prompt: str) -> str:
        """Generate completion using Ollama."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Ollama API error: {response.status_code}")
            
            result = response.json()
            return result.get("response", "")


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
    
    async def complete(self, prompt: str) -> str:
        """Generate completion using OpenAI."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI API error: {response.status_code}")
            
            result = response.json()
            return result["choices"][0]["message"]["content"]


class RegexEntityExtractor:
    """Fast regex-based entity extraction for common patterns."""
    
    PATTERNS = {
        EntityType.EMAIL: r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        EntityType.PHONE: r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        EntityType.URL: r"https?://[^\s<>\"{}|\\^`\[\]]+",
        EntityType.IP_ADDRESS: r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        EntityType.MONEY: r"\$[\d,]+(?:\.\d{2})?|\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|EUR|GBP|JPY)",
        EntityType.DATE: r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
    }
    
    def extract(self, text: str) -> list[ExtractedEntity]:
        """Extract entities using regex patterns."""
        entities = []
        
        for entity_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Get surrounding context
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                
                entity = ExtractedEntity(
                    entity_type=entity_type,
                    value=match.group(),
                    confidence=0.9,  # High confidence for regex matches
                    context=context,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
                entities.append(entity)
        
        return entities


class IntelligenceParser:
    """LLM-powered intelligence parser for categorizing unstructured data."""
    
    ENTITY_EXTRACTION_PROMPT = """Analyze the following text and extract entities.
Return a JSON array of entities with format:
[{{"type": "person|organization|location|financial|technology|legal", "value": "...", "confidence": 0.0-1.0, "context": "..."}}]

Text to analyze:
{text}

Return ONLY valid JSON, no other text."""

    RELATIONSHIP_PROMPT = """Given these entities:
{entities}

Identify relationships between them from the text:
{text}

Return JSON array:
[{{"source": "entity1", "target": "entity2", "relationship": "type", "confidence": 0.0-1.0, "evidence": "..."}}]

Return ONLY valid JSON."""

    RISK_ANALYSIS_PROMPT = """Analyze this content for potential risks, red flags, or anomalies:
{text}

Categories to look for:
- Financial irregularities
- Legal/compliance issues
- Security vulnerabilities
- Reputational risks
- Operational concerns

Return JSON array:
[{{"risk_type": "...", "severity": "low|medium|high|critical", "description": "...", "evidence": ["..."], "confidence": 0.0-1.0}}]

Return ONLY valid JSON."""

    ASSET_INVENTORY_PROMPT = """Extract technology assets, servers, and infrastructure from:
{text}

Look for:
- Software/applications
- Servers/hosts
- Cloud services
- APIs
- Databases
- Network devices

Return JSON:
[{{"asset_type": "...", "name": "...", "version": "...", "details": {{}}, "confidence": 0.0-1.0}}]

Return ONLY valid JSON."""

    CATEGORIZATION_PROMPT = """Categorize this content into ONE of these categories:
- entity_graph: Contains relationships between organizations/people
- risk_vector: Contains financial anomalies or legal issues
- asset_inventory: Contains technology/infrastructure information
- financial_data: Contains financial reports or data
- metadata: Contains document metadata
- unclassified: None of the above

Content:
{text}

Return ONLY the category name."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
    ) -> None:
        settings = get_settings()
        
        if provider:
            self._provider = provider
        elif settings.llm_provider == "openai" and settings.openai_api_key:
            self._provider = OpenAIProvider(settings.openai_api_key)
        else:
            self._provider = OllamaProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            )
        
        self._regex_extractor = RegexEntityExtractor()
        
        logger.info(
            "intelligence_parser_initialized",
            provider=type(self._provider).__name__,
        )
    
    def _parse_json_response(self, response: str) -> Any:
        """Safely parse JSON from LLM response."""
        # Try to find JSON in the response
        response = response.strip()
        
        # Handle markdown code blocks
        if "```json" in response:
            match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if match:
                response = match.group(1)
        elif "```" in response:
            match = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
            if match:
                response = match.group(1)
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to find array or object
            array_match = re.search(r"\[.*\]", response, re.DOTALL)
            if array_match:
                try:
                    return json.loads(array_match.group())
                except json.JSONDecodeError:
                    pass
            
            obj_match = re.search(r"\{.*\}", response, re.DOTALL)
            if obj_match:
                try:
                    return json.loads(obj_match.group())
                except json.JSONDecodeError:
                    pass
        
        return []
    
    async def categorize(self, text: str) -> IntelligenceCategory:
        """Categorize content using LLM."""
        # Truncate long texts
        truncated = text[:4000] if len(text) > 4000 else text
        
        try:
            prompt = self.CATEGORIZATION_PROMPT.format(text=truncated)
            response = await self._provider.complete(prompt)
            
            category_map = {
                "entity_graph": IntelligenceCategory.ENTITY_GRAPH,
                "risk_vector": IntelligenceCategory.RISK_VECTOR,
                "asset_inventory": IntelligenceCategory.ASSET_INVENTORY,
                "financial_data": IntelligenceCategory.FINANCIAL_DATA,
                "metadata": IntelligenceCategory.METADATA,
            }
            
            response_lower = response.lower().strip()
            for key, category in category_map.items():
                if key in response_lower:
                    return category
            
            return IntelligenceCategory.UNCLASSIFIED
            
        except Exception as e:
            logger.error("categorization_failed", error=str(e))
            return IntelligenceCategory.UNCLASSIFIED
    
    async def extract_entities(self, text: str) -> list[ExtractedEntity]:
        """Extract entities using both regex and LLM."""
        # Fast regex extraction
        regex_entities = self._regex_extractor.extract(text)
        
        # LLM extraction for semantic entities
        truncated = text[:4000] if len(text) > 4000 else text
        
        try:
            prompt = self.ENTITY_EXTRACTION_PROMPT.format(text=truncated)
            response = await self._provider.complete(prompt)
            llm_entities_raw = self._parse_json_response(response)
            
            llm_entities = []
            for e in llm_entities_raw:
                if isinstance(e, dict) and "type" in e and "value" in e:
                    try:
                        entity_type = EntityType(e["type"].lower())
                    except ValueError:
                        entity_type = EntityType.ORGANIZATION
                    
                    llm_entities.append(ExtractedEntity(
                        entity_type=entity_type,
                        value=e["value"],
                        confidence=float(e.get("confidence", 0.7)),
                        context=e.get("context", ""),
                    ))
            
            # Merge and deduplicate
            all_entities = regex_entities + llm_entities
            seen_values = set()
            unique_entities = []
            
            for entity in all_entities:
                if entity.value.lower() not in seen_values:
                    seen_values.add(entity.value.lower())
                    unique_entities.append(entity)
            
            return unique_entities
            
        except Exception as e:
            logger.error("entity_extraction_failed", error=str(e))
            return regex_entities
    
    async def analyze_risks(self, text: str) -> list[RiskVector]:
        """Analyze content for risks and anomalies."""
        truncated = text[:4000] if len(text) > 4000 else text
        
        try:
            prompt = self.RISK_ANALYSIS_PROMPT.format(text=truncated)
            response = await self._provider.complete(prompt)
            risks_raw = self._parse_json_response(response)
            
            risks = []
            for r in risks_raw:
                if isinstance(r, dict) and "risk_type" in r:
                    risks.append(RiskVector(
                        risk_type=r["risk_type"],
                        severity=r.get("severity", "medium"),
                        description=r.get("description", ""),
                        evidence=r.get("evidence", []),
                        confidence=float(r.get("confidence", 0.5)),
                    ))
            
            return risks
            
        except Exception as e:
            logger.error("risk_analysis_failed", error=str(e))
            return []
    
    async def extract_assets(self, text: str) -> list[AssetInventoryItem]:
        """Extract asset inventory from content."""
        truncated = text[:4000] if len(text) > 4000 else text
        
        try:
            prompt = self.ASSET_INVENTORY_PROMPT.format(text=truncated)
            response = await self._provider.complete(prompt)
            assets_raw = self._parse_json_response(response)
            
            assets = []
            for a in assets_raw:
                if isinstance(a, dict) and "asset_type" in a:
                    assets.append(AssetInventoryItem(
                        asset_type=a["asset_type"],
                        name=a.get("name", "unknown"),
                        version=a.get("version"),
                        details=a.get("details", {}),
                        source="llm_extraction",
                        confidence=float(a.get("confidence", 0.5)),
                    ))
            
            return assets
            
        except Exception as e:
            logger.error("asset_extraction_failed", error=str(e))
            return []
    
    async def analyze_record(self, record: MinedRecord) -> IntelligenceReport:
        """Perform complete intelligence analysis on a record."""
        # Decode content if bytes
        if isinstance(record.content, bytes):
            try:
                text = record.content.decode("utf-8")
            except UnicodeDecodeError:
                text = record.content.decode("latin-1")
        else:
            text = record.content
        
        # Run analyses in parallel
        category_task = self.categorize(text)
        entities_task = self.extract_entities(text)
        risks_task = self.analyze_risks(text)
        assets_task = self.extract_assets(text)
        
        category, entities, risks, assets = await asyncio.gather(
            category_task,
            entities_task,
            risks_task,
            assets_task,
        )
        
        # Update record category
        record.intelligence_category = category
        record.extracted_entities = [
            {
                "type": e.entity_type.value,
                "value": e.value,
                "confidence": e.confidence,
            }
            for e in entities
        ]
        
        # Calculate risk score
        if risks:
            severity_scores = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
            max_severity = max(severity_scores.get(r.severity, 0) for r in risks)
            record.risk_score = max_severity
        
        # Generate summary
        summary = f"Analyzed document from {record.source_provenance.domain}. "
        summary += f"Found {len(entities)} entities, {len(risks)} risk vectors, "
        summary += f"and {len(assets)} assets. Category: {category.value}"
        
        report = IntelligenceReport(
            record_id=record.record_id,
            source_url=record.source_provenance.url,
            analyzed_at=datetime.now(timezone.utc),
            category=category,
            entities=entities,
            relationships=[],  # Would need additional processing
            risk_vectors=risks,
            asset_inventory=assets,
            summary=summary,
        )
        
        logger.info(
            "intelligence_analysis_complete",
            record_id=record.record_id,
            category=category.value,
            entities=len(entities),
            risks=len(risks),
            assets=len(assets),
        )
        
        return report
