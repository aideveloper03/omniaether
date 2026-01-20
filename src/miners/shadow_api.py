"""Shadow API Interception Engine for AETHER-MINE.

Uses Playwright's request.continue() and response.json() hooks to:
- Identify and record hidden JSON endpoints (XHR, Fetch)
- Extract API schemas
- Identify authentication headers (Bearer tokens, custom IDs)
- Clone request logic into high-speed httpx workers
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse, parse_qs

import httpx
import structlog
from playwright.async_api import (
    async_playwright,
    Page,
    Request,
    Response,
    Route,
    Browser,
    BrowserContext,
)

from src.core.config import get_settings
from src.core.models import (
    APISchema,
    RequestMethod,
    MinedRecord,
    SourceProvenance,
    FallbackTier,
)
from src.core.telemetry import get_telemetry, create_trace_id


logger = structlog.get_logger(__name__)


@dataclass
class InterceptedRequest:
    """Captured request from interception."""
    
    url: str
    method: str
    headers: dict[str, str]
    post_data: str | None
    resource_type: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class InterceptedResponse:
    """Captured response from interception."""
    
    url: str
    status: int
    headers: dict[str, str]
    body: bytes | None
    content_type: str
    is_json: bool
    json_body: dict[str, Any] | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def infer_json_schema(data: Any, max_depth: int = 5) -> dict[str, Any]:
    """Infer JSON schema from data structure."""
    if max_depth <= 0:
        return {"type": "any"}
    
    if data is None:
        return {"type": "null"}
    elif isinstance(data, bool):
        return {"type": "boolean"}
    elif isinstance(data, int):
        return {"type": "integer"}
    elif isinstance(data, float):
        return {"type": "number"}
    elif isinstance(data, str):
        # Try to detect special string types
        if re.match(r"^\d{4}-\d{2}-\d{2}", data):
            return {"type": "string", "format": "date-time"}
        elif re.match(r"^[a-f0-9-]{36}$", data.lower()):
            return {"type": "string", "format": "uuid"}
        elif re.match(r"^https?://", data):
            return {"type": "string", "format": "uri"}
        elif re.match(r"^[^@]+@[^@]+\.[^@]+$", data):
            return {"type": "string", "format": "email"}
        return {"type": "string"}
    elif isinstance(data, list):
        if not data:
            return {"type": "array", "items": {"type": "any"}}
        # Infer from first item
        return {"type": "array", "items": infer_json_schema(data[0], max_depth - 1)}
    elif isinstance(data, dict):
        properties = {}
        for key, value in data.items():
            properties[key] = infer_json_schema(value, max_depth - 1)
        return {"type": "object", "properties": properties}
    else:
        return {"type": "unknown"}


class ShadowAPIInterceptor:
    """Protocol-level interceptor for discovering hidden API endpoints."""
    
    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30000,
        capture_resource_types: list[str] | None = None,
    ) -> None:
        settings = get_settings()
        self._headless = headless if headless is not None else settings.browser_headless
        self._timeout = timeout_ms or settings.browser_timeout_ms
        self._capture_types = capture_resource_types or ["xhr", "fetch"]
        
        self._intercepted_requests: list[InterceptedRequest] = []
        self._intercepted_responses: list[InterceptedResponse] = []
        self._discovered_apis: dict[str, APISchema] = {}
        self._telemetry = get_telemetry()
        
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        
        logger.info(
            "shadow_api_interceptor_initialized",
            headless=self._headless,
            capture_types=self._capture_types,
        )
    
    async def start(self) -> None:
        """Start the browser and create context."""
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()
        
        # Set up request interception
        await self._page.route("**/*", self._handle_route)
        
        # Set up response listener
        self._page.on("response", self._handle_response)
        
        logger.info("browser_started")
    
    async def stop(self) -> None:
        """Stop the browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
            self._page = None
        logger.info("browser_stopped")
    
    async def _handle_route(self, route: Route) -> None:
        """Handle route interception - capture request details."""
        request = route.request
        
        # Capture request if it's a target type
        if request.resource_type in self._capture_types:
            intercepted = InterceptedRequest(
                url=request.url,
                method=request.method,
                headers=dict(request.headers),
                post_data=request.post_data,
                resource_type=request.resource_type,
            )
            self._intercepted_requests.append(intercepted)
            
            logger.debug(
                "request_intercepted",
                url=request.url,
                method=request.method,
                type=request.resource_type,
            )
        
        # Continue the request
        await route.continue_()
    
    async def _handle_response(self, response: Response) -> None:
        """Handle response - capture and analyze JSON responses."""
        request = response.request
        
        # Only process target resource types
        if request.resource_type not in self._capture_types:
            return
        
        content_type = response.headers.get("content-type", "")
        is_json = "application/json" in content_type or "text/json" in content_type
        
        body = None
        json_body = None
        
        try:
            body = await response.body()
            if is_json and body:
                json_body = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.debug("response_body_error", url=response.url, error=str(e))
        
        intercepted = InterceptedResponse(
            url=response.url,
            status=response.status,
            headers=dict(response.headers),
            body=body,
            content_type=content_type,
            is_json=is_json,
            json_body=json_body,
        )
        self._intercepted_responses.append(intercepted)
        
        # If JSON, extract API schema
        if is_json and json_body is not None:
            self._extract_api_schema(request, response, json_body)
        
        logger.debug(
            "response_intercepted",
            url=response.url,
            status=response.status,
            is_json=is_json,
        )
    
    def _extract_api_schema(
        self,
        request: Request,
        response: Response,
        json_body: Any,
    ) -> APISchema:
        """Extract API schema from intercepted request/response."""
        parsed_url = urlparse(request.url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        endpoint = parsed_url.path
        query_params = parse_qs(parsed_url.query)
        
        # Flatten query params
        flat_params = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
        
        # Identify authentication
        auth_type = None
        auth_header = None
        request_headers = dict(request.headers)
        
        if "authorization" in request_headers:
            auth_header = "authorization"
            auth_value = request_headers["authorization"]
            if auth_value.lower().startswith("bearer "):
                auth_type = "Bearer"
            elif auth_value.lower().startswith("basic "):
                auth_type = "Basic"
            else:
                auth_type = "Custom"
        elif "x-api-key" in request_headers:
            auth_type = "API-Key"
            auth_header = "x-api-key"
        elif "x-auth-token" in request_headers:
            auth_type = "Token"
            auth_header = "x-auth-token"
        
        # Infer request body schema if POST/PUT
        request_body_schema = None
        if request.post_data:
            try:
                post_json = json.loads(request.post_data)
                request_body_schema = infer_json_schema(post_json)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Infer response schema
        response_body_schema = infer_json_schema(json_body)
        
        schema = APISchema(
            endpoint=endpoint,
            base_url=base_url,
            method=RequestMethod(request.method),
            request_headers={
                k: v for k, v in request_headers.items()
                if k.lower() not in ["cookie", "authorization"]  # Sanitize
            },
            response_headers={
                k: v for k, v in response.headers.items()
                if k.lower() not in ["set-cookie"]
            },
            query_params=flat_params,
            request_body_schema=request_body_schema,
            response_body_schema=response_body_schema,
            auth_type=auth_type,
            auth_header=auth_header,
            content_type=response.headers.get("content-type", "application/json"),
        )
        
        # Store by endpoint
        self._discovered_apis[schema.full_url] = schema
        
        logger.info(
            "api_schema_extracted",
            endpoint=endpoint,
            method=request.method,
            auth_type=auth_type,
        )
        
        return schema
    
    async def navigate_and_intercept(
        self,
        url: str,
        wait_for: str = "networkidle",
        additional_wait_ms: int = 2000,
    ) -> list[APISchema]:
        """Navigate to URL and intercept all API calls.
        
        Returns list of discovered API schemas.
        """
        if not self._page:
            await self.start()
        
        trace_id = create_trace_id()
        
        logger.info(
            "navigation_started",
            trace_id=trace_id,
            url=url,
        )
        
        # Clear previous captures
        self._intercepted_requests.clear()
        self._intercepted_responses.clear()
        self._discovered_apis.clear()
        
        try:
            await self._page.goto(url, wait_until=wait_for, timeout=self._timeout)
            
            # Additional wait to capture lazy-loaded APIs
            await asyncio.sleep(additional_wait_ms / 1000)
            
            logger.info(
                "navigation_complete",
                trace_id=trace_id,
                url=url,
                apis_discovered=len(self._discovered_apis),
                requests_captured=len(self._intercepted_requests),
            )
            
            return list(self._discovered_apis.values())
            
        except Exception as e:
            logger.error(
                "navigation_failed",
                trace_id=trace_id,
                url=url,
                error=str(e),
            )
            raise
    
    async def clone_to_httpx(
        self,
        schema: APISchema,
        override_headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        """Clone API request to high-speed httpx worker.
        
        Bypasses browser overhead for direct API access.
        """
        headers = dict(schema.request_headers)
        if override_headers:
            headers.update(override_headers)
        
        # Remove browser-specific headers
        headers.pop("accept-encoding", None)
        headers.pop("connection", None)
        
        trace_id = create_trace_id()
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = schema.full_url
            if schema.query_params:
                url += "?" + "&".join(
                    f"{k}={v}" for k, v in schema.query_params.items()
                )
            
            logger.info(
                "httpx_request",
                trace_id=trace_id,
                url=url,
                method=schema.method.value,
            )
            
            if schema.method == RequestMethod.GET:
                response = await client.get(url, headers=headers)
            elif schema.method == RequestMethod.POST:
                response = await client.post(url, headers=headers)
            elif schema.method == RequestMethod.PUT:
                response = await client.put(url, headers=headers)
            elif schema.method == RequestMethod.DELETE:
                response = await client.delete(url, headers=headers)
            else:
                response = await client.request(
                    schema.method.value,
                    url,
                    headers=headers,
                )
            
            logger.info(
                "httpx_response",
                trace_id=trace_id,
                url=url,
                status=response.status_code,
            )
            
            return response
    
    def get_discovered_apis(self) -> list[APISchema]:
        """Get all discovered API schemas."""
        return list(self._discovered_apis.values())
    
    def get_intercepted_responses(self) -> list[InterceptedResponse]:
        """Get all intercepted responses."""
        return list(self._intercepted_responses)
    
    async def extract_to_records(
        self,
        domain: str,
    ) -> list[MinedRecord]:
        """Convert intercepted responses to MinedRecord objects."""
        records = []
        
        for response in self._intercepted_responses:
            if not response.is_json or response.body is None:
                continue
            
            content_hash = MinedRecord.compute_content_hash(response.body)
            
            provenance = SourceProvenance(
                url=response.url,
                domain=domain,
                discovery_method="shadow_api_interception",
                retrieval_tier=FallbackTier.SHADOW_API,
            )
            
            record = MinedRecord(
                source_provenance=provenance,
                content_hash=content_hash,
                content_type=response.content_type,
                content=response.body,
                content_size_bytes=len(response.body),
                metadata={
                    "status_code": response.status,
                    "headers": response.headers,
                    "is_json": True,
                },
            )
            records.append(record)
        
        logger.info(
            "records_extracted",
            count=len(records),
            domain=domain,
        )
        
        return records


class HighSpeedAPIWorker:
    """High-speed worker for direct API fetching without browser overhead.
    
    Uses cloned API schemas from ShadowAPIInterceptor.
    """
    
    def __init__(
        self,
        max_concurrent: int = 10,
        timeout: float = 30.0,
    ) -> None:
        self._max_concurrent = max_concurrent
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._telemetry = get_telemetry()
        
        logger.info(
            "api_worker_initialized",
            max_concurrent=max_concurrent,
        )
    
    async def fetch(
        self,
        schema: APISchema,
        override_params: dict[str, str] | None = None,
        override_headers: dict[str, str] | None = None,
    ) -> tuple[httpx.Response, float]:
        """Fetch API endpoint with telemetry.
        
        Returns (response, latency_ms)
        """
        import time
        
        async with self._semaphore:
            headers = dict(schema.request_headers)
            if override_headers:
                headers.update(override_headers)
            
            params = dict(schema.query_params)
            if override_params:
                params.update(override_params)
            
            url = schema.full_url
            
            start = time.perf_counter()
            
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    schema.method.value,
                    url,
                    headers=headers,
                    params=params,
                )
            
            latency_ms = (time.perf_counter() - start) * 1000
            
            return response, latency_ms
    
    async def fetch_batch(
        self,
        schemas: list[APISchema],
        callback: Callable[[httpx.Response, APISchema], Any] | None = None,
    ) -> list[tuple[APISchema, httpx.Response, float]]:
        """Fetch multiple API endpoints concurrently."""
        async def fetch_one(schema: APISchema) -> tuple[APISchema, httpx.Response, float]:
            response, latency = await self.fetch(schema)
            if callback:
                await callback(response, schema)
            return schema, response, latency
        
        tasks = [fetch_one(schema) for schema in schemas]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = [
            r for r in results
            if not isinstance(r, Exception)
        ]
        
        return valid_results
