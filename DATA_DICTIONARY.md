# Data Dictionary

All data is stored in Parquet format with Snappy compression.

## Common Fields (BaseRecord)
| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | Timestamp | UTC time of extraction |
| `source_provenance` | String | Source URL/Origin (Non-empty) |
| `content_hash` | String | SHA256 Hash of content (Dedup key) |
| `trace_id` | String | Lineage ID |

## ShadowApiRecord
| Field | Type | Description |
|-------|------|-------------|
| `url` | String | API Endpoint URL |
| `method` | String | HTTP Method (GET/POST) |
| `headers` | Map<Str, Str> | Request Headers |
| `payload` | JSON | Request Body |
| `response_schema` | JSON | Inferred Schema of Response |
| `response_sample` | JSON | Sample Data |
| `is_authenticated` | Boolean | Requires Auth? |
| `auth_token_type` | String | Bearer/Basic/Cookie |

## DocumentRecord
| Field | Type | Description |
|-------|------|-------------|
| `file_name` | String | Name of file |
| `file_type` | String | MIME type |
| `file_size_bytes` | Int | Size in bytes |
| `s3_bucket` | String | Bucket URL (if applicable) |
| `metadata` | JSON | Extra metadata (HTTP Status, Headers) |
| `text_content` | String | Extracted text (if parsed) |

## IntelligenceRecord
| Field | Type | Description |
|-------|------|-------------|
| `category` | String | Entity_Graph, Risk_Vectors, Asset_Inventory |
| `raw_data_reference` | String | Hash of source record |
| `insights` | JSON | LLM extracted insights |
| `entities` | List[Relation] | Graph edges |
