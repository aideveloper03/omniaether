import json
from datetime import datetime
from typing import Optional, Any
from playwright.async_api import Page, Request, Response
from loguru import logger
from src.storage.models import ShadowApiRecord, compute_content_hash
from src.storage.parquet_stream import stream_writer
from src.core.telemetry import get_trace_id, generate_trace_id

class ShadowApiMiner:
    def __init__(self):
        pass

    async def start_interception(self, page: Page, target_url: str):
        """
        Navigate to target_url and intercept all API traffic.
        """
        # Ensure trace id
        tid = get_trace_id() or generate_trace_id()
        
        # Setup handlers
        page.on("request", self._handle_request)
        page.on("response", self._handle_response)
        
        try:
            logger.info(f"Navigating to {target_url} with Shadow Interceptor")
            await page.goto(target_url, wait_until="networkidle")
            # Wait for some time to allow background requests
            await page.wait_for_timeout(5000) 
            
            # Scroll to trigger lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            
        except Exception as e:
            logger.error(f"Error during Shadow API interception: {e}")

    async def _handle_request(self, request: Request):
        # We generally just monitor requests, but could abort/continue here
        pass

    async def _handle_response(self, response: Response):
        """
        Process response to identify Shadow APIs.
        """
        request = response.request
        resource_type = request.resource_type
        
        # Filter for data-like responses
        if resource_type in ["xhr", "fetch"] or "json" in response.headers.get("content-type", ""):
            try:
                # Attempt to parse JSON
                text = await response.text()
                if not text:
                    return
                
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    return # Not JSON
                
                # It's a valid JSON response. Capture it.
                await self._capture_shadow_api(request, response, data)
                
            except Exception as e:
                # Often responses fail to load body if redirected or failed
                pass

    async def _capture_shadow_api(self, request: Request, response: Response, data: dict):
        try:
            # Extract headers and potential auth
            headers = request.headers
            auth_type = None
            if "authorization" in headers:
                auth_type = headers["authorization"].split(" ")[0]
            
            # Create Record
            record = ShadowApiRecord(
                timestamp=datetime.utcnow(),
                source_provenance=request.url,
                content_hash=compute_content_hash(data),
                trace_id=get_trace_id(),
                url=request.url,
                method=request.method,
                headers=dict(headers),
                payload=None, # Need to extract payload if POST
                response_schema=self._extract_schema(data),
                response_sample=data, # Warning: Might be large, should truncate in prod
                is_authenticated=auth_type is not None,
                auth_token_type=auth_type
            )
            
            stream_writer.add_record(record)
            logger.info(f"Captured Shadow API: {request.url}")
            
        except Exception as e:
            logger.error(f"Failed to capture shadow API record: {e}")

    def _extract_schema(self, data: Any) -> dict:
        """
        Generate a simple schema from the JSON data.
        """
        if isinstance(data, dict):
            return {k: type(v).__name__ for k, v in data.items()}
        elif isinstance(data, list) and len(data) > 0:
            return {"[list]": self._extract_schema(data[0])}
        return {"type": type(data).__name__}
