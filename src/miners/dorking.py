"""Dorking Swarm for AETHER-MINE.

Automated generation and execution of advanced search queries:
- Google Dorks (filetype:, intitle:, site:, etc.)
- Bing Dorks
- DuckDuckGo queries
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urljoin

import httpx
import structlog

from src.core.models import MinedRecord, SourceProvenance, FallbackTier
from src.core.telemetry import get_telemetry, create_trace_id


logger = structlog.get_logger(__name__)


@dataclass
class DorkResult:
    """Result from a dork query."""
    
    query: str
    search_engine: str
    url: str
    title: str
    snippet: str
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass 
class DorkQuery:
    """A dork query configuration."""
    
    template: str
    category: str
    description: str
    risk_level: str  # low, medium, high, critical
    
    def build(self, target: str) -> str:
        """Build the query with target substitution."""
        return self.template.format(target=target)


class DorkLibrary:
    """Library of pre-defined dork queries."""
    
    # File exposure dorks
    FILE_DORKS = [
        DorkQuery(
            template='site:{target} filetype:env',
            category="credentials",
            description="Environment files with potential secrets",
            risk_level="critical",
        ),
        DorkQuery(
            template='site:{target} filetype:sql',
            category="database",
            description="SQL dump files",
            risk_level="critical",
        ),
        DorkQuery(
            template='site:{target} filetype:log',
            category="logs",
            description="Log files with potential sensitive info",
            risk_level="high",
        ),
        DorkQuery(
            template='site:{target} filetype:conf OR filetype:config',
            category="config",
            description="Configuration files",
            risk_level="high",
        ),
        DorkQuery(
            template='site:{target} filetype:bak OR filetype:backup',
            category="backup",
            description="Backup files",
            risk_level="high",
        ),
        DorkQuery(
            template='site:{target} filetype:xlsx OR filetype:csv',
            category="data",
            description="Spreadsheet data files",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:{target} filetype:pdf',
            category="documents",
            description="PDF documents",
            risk_level="low",
        ),
        DorkQuery(
            template='site:{target} filetype:doc OR filetype:docx',
            category="documents",
            description="Word documents",
            risk_level="low",
        ),
    ]
    
    # Directory listing dorks
    DIRECTORY_DORKS = [
        DorkQuery(
            template='site:{target} intitle:"index of /"',
            category="directory_listing",
            description="Open directory listings",
            risk_level="high",
        ),
        DorkQuery(
            template='site:{target} intitle:"index of" "parent directory"',
            category="directory_listing",
            description="Apache directory listings",
            risk_level="high",
        ),
        DorkQuery(
            template='site:{target} intitle:"Directory listing for"',
            category="directory_listing",
            description="Python/Django directory listings",
            risk_level="high",
        ),
    ]
    
    # Cloud storage dorks
    CLOUD_DORKS = [
        DorkQuery(
            template='site:s3.amazonaws.com "{target}"',
            category="cloud",
            description="S3 buckets mentioning target",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:blob.core.windows.net "{target}"',
            category="cloud",
            description="Azure blobs mentioning target",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:storage.googleapis.com "{target}"',
            category="cloud",
            description="GCS buckets mentioning target",
            risk_level="medium",
        ),
        DorkQuery(
            template='"{target}" site:pastebin.com',
            category="leak",
            description="Pastebin leaks",
            risk_level="high",
        ),
        DorkQuery(
            template='"{target}" site:github.com',
            category="code",
            description="GitHub code mentions",
            risk_level="medium",
        ),
    ]
    
    # Error/debug dorks
    ERROR_DORKS = [
        DorkQuery(
            template='site:{target} "error" OR "exception" filetype:log',
            category="errors",
            description="Error logs",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:{target} "stack trace" OR "traceback"',
            category="errors",
            description="Stack traces",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:{target} "debug" OR "DEBUG=True"',
            category="debug",
            description="Debug mode enabled",
            risk_level="high",
        ),
    ]
    
    # Admin/login dorks
    ADMIN_DORKS = [
        DorkQuery(
            template='site:{target} inurl:admin',
            category="admin",
            description="Admin pages",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:{target} inurl:login OR inurl:signin',
            category="auth",
            description="Login pages",
            risk_level="low",
        ),
        DorkQuery(
            template='site:{target} inurl:dashboard',
            category="admin",
            description="Dashboard pages",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:{target} intitle:"phpMyAdmin"',
            category="database",
            description="phpMyAdmin instances",
            risk_level="critical",
        ),
    ]
    
    # API exposure dorks
    API_DORKS = [
        DorkQuery(
            template='site:{target} inurl:api',
            category="api",
            description="API endpoints",
            risk_level="low",
        ),
        DorkQuery(
            template='site:{target} inurl:swagger OR inurl:api-docs',
            category="api",
            description="Swagger/API documentation",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:{target} inurl:graphql',
            category="api",
            description="GraphQL endpoints",
            risk_level="medium",
        ),
        DorkQuery(
            template='site:{target} filetype:json "api" OR "apikey"',
            category="api",
            description="JSON files with API references",
            risk_level="high",
        ),
    ]
    
    @classmethod
    def get_all_dorks(cls) -> list[DorkQuery]:
        """Get all dork queries."""
        return (
            cls.FILE_DORKS
            + cls.DIRECTORY_DORKS
            + cls.CLOUD_DORKS
            + cls.ERROR_DORKS
            + cls.ADMIN_DORKS
            + cls.API_DORKS
        )
    
    @classmethod
    def get_by_category(cls, category: str) -> list[DorkQuery]:
        """Get dorks by category."""
        return [d for d in cls.get_all_dorks() if d.category == category]
    
    @classmethod
    def get_by_risk_level(cls, min_level: str) -> list[DorkQuery]:
        """Get dorks at or above a risk level."""
        levels = ["low", "medium", "high", "critical"]
        min_idx = levels.index(min_level)
        return [
            d for d in cls.get_all_dorks()
            if levels.index(d.risk_level) >= min_idx
        ]


class SearchEngineParser:
    """Parser for search engine result pages."""
    
    @staticmethod
    def parse_google(html: str) -> list[dict[str, str]]:
        """Parse Google search results."""
        results = []
        
        # Extract result blocks
        # Pattern for Google result links
        url_pattern = r'<a href="([^"]+)"[^>]*><h3[^>]*>([^<]+)</h3>'
        snippet_pattern = r'<span class="[^"]*">([^<]{50,})</span>'
        
        urls = re.findall(url_pattern, html)
        snippets = re.findall(snippet_pattern, html)
        
        for i, (url, title) in enumerate(urls):
            if url.startswith("/url?q="):
                url = url[7:].split("&")[0]
            
            snippet = snippets[i] if i < len(snippets) else ""
            
            if url.startswith("http"):
                results.append({
                    "url": url,
                    "title": title,
                    "snippet": snippet,
                })
        
        return results
    
    @staticmethod
    def parse_bing(html: str) -> list[dict[str, str]]:
        """Parse Bing search results."""
        results = []
        
        # Bing result pattern
        pattern = r'<a href="([^"]+)"[^>]*><h2>([^<]+)</h2>'
        matches = re.findall(pattern, html)
        
        for url, title in matches:
            if url.startswith("http"):
                results.append({
                    "url": url,
                    "title": title,
                    "snippet": "",
                })
        
        return results
    
    @staticmethod
    def parse_duckduckgo(html: str) -> list[dict[str, str]]:
        """Parse DuckDuckGo search results."""
        results = []
        
        # DDG result pattern
        pattern = r'<a class="result__a" href="([^"]+)">([^<]+)</a>'
        matches = re.findall(pattern, html)
        
        for url, title in matches:
            results.append({
                "url": url,
                "title": title,
                "snippet": "",
            })
        
        return results


class DorkingSwarm:
    """Automated dorking swarm for multi-engine search queries."""
    
    SEARCH_ENGINES = {
        "google": {
            "url": "https://www.google.com/search?q={query}&num=100",
            "parser": SearchEngineParser.parse_google,
        },
        "bing": {
            "url": "https://www.bing.com/search?q={query}&count=50",
            "parser": SearchEngineParser.parse_bing,
        },
        "duckduckgo": {
            "url": "https://html.duckduckgo.com/html/?q={query}",
            "parser": SearchEngineParser.parse_duckduckgo,
        },
    }
    
    def __init__(
        self,
        max_concurrent: int = 5,
        timeout: float = 30.0,
        delay_between_requests: float = 2.0,
    ) -> None:
        self._max_concurrent = max_concurrent
        self._timeout = timeout
        self._delay = delay_between_requests
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._telemetry = get_telemetry()
        
        self._results: list[DorkResult] = []
        self._library = DorkLibrary()
        
        # User agents for different engines
        self._user_agents = {
            "google": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "bing": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
            ),
            "duckduckgo": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
                "Gecko/20100101 Firefox/123.0"
            ),
        }
        
        logger.info(
            "dorking_swarm_initialized",
            max_concurrent=max_concurrent,
        )
    
    async def _execute_search(
        self,
        query: str,
        engine: str,
    ) -> list[dict[str, str]]:
        """Execute a single search query."""
        async with self._semaphore:
            config = self.SEARCH_ENGINES[engine]
            url = config["url"].format(query=quote_plus(query))
            
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(
                        url,
                        headers={
                            "User-Agent": self._user_agents[engine],
                            "Accept": "text/html,application/xhtml+xml",
                            "Accept-Language": "en-US,en;q=0.9",
                        },
                    )
                    
                    if response.status_code != 200:
                        logger.warning(
                            "search_failed",
                            engine=engine,
                            status=response.status_code,
                        )
                        return []
                    
                    results = config["parser"](response.text)
                    
                    logger.debug(
                        "search_complete",
                        engine=engine,
                        query=query[:50],
                        results=len(results),
                    )
                    
                    # Rate limiting delay
                    await asyncio.sleep(self._delay)
                    
                    return results
                    
            except httpx.HTTPError as e:
                logger.error("search_error", engine=engine, error=str(e))
                return []
    
    async def execute_dork(
        self,
        dork: DorkQuery,
        target: str,
        engines: list[str] | None = None,
    ) -> list[DorkResult]:
        """Execute a dork query across search engines."""
        if engines is None:
            engines = ["google", "duckduckgo"]  # Default to less aggressive
        
        query = dork.build(target)
        results = []
        
        for engine in engines:
            search_results = await self._execute_search(query, engine)
            
            for result in search_results:
                dork_result = DorkResult(
                    query=query,
                    search_engine=engine,
                    url=result["url"],
                    title=result["title"],
                    snippet=result.get("snippet", ""),
                )
                results.append(dork_result)
                self._results.append(dork_result)
        
        return results
    
    async def swarm_target(
        self,
        target: str,
        categories: list[str] | None = None,
        min_risk_level: str = "medium",
        engines: list[str] | None = None,
    ) -> dict[str, list[DorkResult]]:
        """Run full dorking swarm against a target.
        
        Args:
            target: Target domain or brand name
            categories: Specific dork categories to use
            min_risk_level: Minimum risk level of dorks to use
            engines: Search engines to use
        """
        trace_id = create_trace_id()
        
        # Select dorks
        if categories:
            dorks = []
            for cat in categories:
                dorks.extend(self._library.get_by_category(cat))
        else:
            dorks = self._library.get_by_risk_level(min_risk_level)
        
        logger.info(
            "swarm_started",
            trace_id=trace_id,
            target=target,
            dork_count=len(dorks),
            engines=engines,
        )
        
        results_by_category: dict[str, list[DorkResult]] = {}
        
        for dork in dorks:
            category_results = await self.execute_dork(dork, target, engines)
            
            if dork.category not in results_by_category:
                results_by_category[dork.category] = []
            
            results_by_category[dork.category].extend(category_results)
        
        total_results = sum(len(r) for r in results_by_category.values())
        
        logger.info(
            "swarm_complete",
            trace_id=trace_id,
            target=target,
            total_results=total_results,
            categories=list(results_by_category.keys()),
        )
        
        return results_by_category
    
    async def verify_and_download(
        self,
        results: list[DorkResult],
        max_size_mb: int = 10,
    ) -> list[MinedRecord]:
        """Verify discovered URLs and download content."""
        records = []
        max_size = max_size_mb * 1024 * 1024
        seen_urls = set()
        
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            for result in results:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                
                try:
                    # HEAD request first to check size
                    head_response = await client.head(result.url)
                    
                    if head_response.status_code != 200:
                        continue
                    
                    content_length = int(
                        head_response.headers.get("content-length", 0)
                    )
                    
                    if content_length > max_size:
                        logger.debug(
                            "skipping_large_file",
                            url=result.url,
                            size=content_length,
                        )
                        continue
                    
                    # Download content
                    response = await client.get(result.url)
                    
                    if response.status_code != 200:
                        continue
                    
                    content = response.content
                    
                    if len(content) > max_size:
                        continue
                    
                    from urllib.parse import urlparse
                    parsed = urlparse(result.url)
                    
                    provenance = SourceProvenance(
                        url=result.url,
                        domain=parsed.netloc,
                        discovery_method=f"dorking_{result.search_engine}",
                        retrieval_tier=FallbackTier.SHADOW_API,
                    )
                    
                    record = MinedRecord(
                        source_provenance=provenance,
                        content_hash=MinedRecord.compute_content_hash(content),
                        content_type=response.headers.get(
                            "content-type",
                            "application/octet-stream",
                        ),
                        content=content,
                        content_size_bytes=len(content),
                        title=result.title,
                        metadata={
                            "dork_query": result.query,
                            "search_engine": result.search_engine,
                            "snippet": result.snippet,
                        },
                    )
                    records.append(record)
                    
                except Exception as e:
                    logger.debug("download_failed", url=result.url, error=str(e))
        
        logger.info("verification_complete", downloaded=len(records))
        return records
    
    def get_all_results(self) -> list[DorkResult]:
        """Get all discovered results."""
        return list(self._results)
    
    def get_results_by_category(self) -> dict[str, list[DorkResult]]:
        """Get results grouped by category."""
        by_category: dict[str, list[DorkResult]] = {}
        
        for result in self._results:
            # Extract category from query
            category = "unknown"
            for dork in self._library.get_all_dorks():
                if dork.template.replace("{target}", "") in result.query:
                    category = dork.category
                    break
            
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(result)
        
        return by_category
