from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict
import hashlib
import json

class BaseRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    timestamp: datetime = Field(..., description="UTC timestamp of extraction")
    source_provenance: str = Field(..., description="URL or origin source of the data")
    content_hash: str = Field(..., description="SHA256 hash of the primary content")
    trace_id: str = Field(..., description="System trace ID for lineage")
    
    @field_validator('source_provenance')
    @classmethod
    def validate_provenance(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("source_provenance cannot be empty")
        return v

    @field_validator('content_hash')
    @classmethod
    def validate_hash(cls, v: str) -> str:
        if len(v) != 64:
            raise ValueError("content_hash must be a valid SHA256 hex string")
        return v

class ShadowApiRecord(BaseRecord):
    """
    Schema for captured API transactions.
    """
    url: str
    method: str
    headers: Dict[str, str]
    payload: Optional[Dict[str, Any]] = None
    response_schema: Dict[str, Any]  # JSON schema of the response
    response_sample: Dict[str, Any]  # Sample data (truncated if necessary)
    is_authenticated: bool = Field(default=False)
    auth_token_type: Optional[str] = None

class DocumentRecord(BaseRecord):
    """
    Schema for discovered documents (PDFs, etc).
    """
    file_name: str
    file_type: str
    file_size_bytes: int
    s3_bucket: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    text_content: str # Extracted text

class EntityRelation(BaseModel):
    source_entity: str
    target_entity: str
    relation_type: str
    confidence: float

class IntelligenceRecord(BaseRecord):
    """
    Schema for processed intelligence.
    """
    category: str  # Entity_Graph, Risk_Vectors, Asset_Inventory
    raw_data_reference: str # content_hash of the source record
    insights: Dict[str, Any]
    entities: List[EntityRelation] = Field(default_factory=list)

def compute_content_hash(content: Any) -> str:
    """Helper to compute SHA256 hash of content."""
    if isinstance(content, (dict, list)):
        encoded = json.dumps(content, sort_keys=True).encode('utf-8')
    elif isinstance(content, str):
        encoded = content.encode('utf-8')
    elif isinstance(content, bytes):
        encoded = content
    else:
        encoded = str(content).encode('utf-8')
    
    return hashlib.sha256(encoded).hexdigest()
