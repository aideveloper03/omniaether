"""Recursive Pattern-Gap Fuzzing for AETHER-MINE.

Discovers unindexed files by:
- Analyzing URL patterns (dates, versions, sequences)
- Generating permutations based on discovered patterns
- Recursively fuzzing to find unlinked resources
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urljoin

import httpx
import structlog

from src.core.config import get_settings
from src.core.models import FuzzPattern, MinedRecord, SourceProvenance, FallbackTier
from src.core.telemetry import get_telemetry, create_trace_id


logger = structlog.get_logger(__name__)


@dataclass
class PatternMatch:
    """A discovered pattern in a URL."""
    
    pattern_type: str  # numeric, date, version, alphanumeric
    original_value: str
    position: int
    regex: str
    template: str
    
    def generate_variants(self, count: int = 20) -> list[str]:
        """Generate variant values based on pattern type."""
        variants = []
        
        if self.pattern_type == "year":
            # Generate years around the original
            try:
                year = int(self.original_value)
                for y in range(year - 5, year + 3):
                    variants.append(str(y))
            except ValueError:
                pass
                
        elif self.pattern_type == "date_ymd":
            # Generate dates around the original
            try:
                date = datetime.strptime(self.original_value, "%Y%m%d")
                for days in range(-365, 365, 30):
                    new_date = date.replace(day=1)  # Simplify
                    variants.append(new_date.strftime("%Y%m%d"))
            except ValueError:
                pass
                
        elif self.pattern_type == "version":
            # Generate version variants
            match = re.match(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", self.original_value)
            if match:
                major = int(match.group(1))
                minor = int(match.group(2) or 0)
                patch = int(match.group(3) or 0)
                
                prefix = "v" if self.original_value.startswith("v") else ""
                
                for m in range(max(0, major - 2), major + 3):
                    for n in range(0, 10):
                        variants.append(f"{prefix}{m}.{n}")
                        variants.append(f"{prefix}{m}.{n}.0")
                        
        elif self.pattern_type == "numeric_sequence":
            # Generate numeric sequences
            try:
                num = int(self.original_value)
                padding = len(self.original_value)
                for n in range(max(0, num - 10), num + 20):
                    variants.append(str(n).zfill(padding))
            except ValueError:
                pass
                
        elif self.pattern_type == "quarter":
            # Financial quarters
            for year in range(2018, 2027):
                for q in ["Q1", "Q2", "Q3", "Q4", "q1", "q2", "q3", "q4"]:
                    variants.append(f"{year}{q}")
                    variants.append(f"{q}{year}")
        
        return list(set(variants))[:count]


class URLPatternAnalyzer:
    """Analyzes URLs to detect fuzzable patterns."""
    
    # Pattern definitions
    PATTERNS = [
        # Year patterns
        (r"(20\d{2})", "year"),
        # Full date patterns
        (r"(\d{4}-\d{2}-\d{2})", "date_iso"),
        (r"(\d{4}\d{2}\d{2})", "date_ymd"),
        (r"(\d{2}-\d{2}-\d{4})", "date_mdy"),
        # Version patterns
        (r"(v\d+\.\d+(?:\.\d+)?)", "version"),
        (r"(v\d+)", "version_major"),
        # Numeric sequences
        (r"_(\d{3,6})(?:\.|_|$)", "numeric_sequence"),
        (r"-(\d{3,6})(?:\.|_|$)", "numeric_sequence"),
        # Quarter patterns
        (r"(20\d{2}[Qq][1-4])", "quarter"),
        (r"([Qq][1-4]20\d{2})", "quarter"),
        # Report/document patterns
        (r"(annual|quarterly|monthly)[-_]?(\d{4})", "report_period"),
        # Alphanumeric IDs
        (r"([a-f0-9]{8,})", "hex_id"),
    ]
    
    def __init__(self) -> None:
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), pattern_type)
            for pattern, pattern_type in self.PATTERNS
        ]
    
    def analyze(self, url: str) -> list[PatternMatch]:
        """Analyze URL and return detected patterns."""
        patterns = []
        
        for regex, pattern_type in self._compiled_patterns:
            for match in regex.finditer(url):
                value = match.group(1)
                start = match.start(1)
                
                # Create template by replacing match with placeholder
                template = url[:start] + "{value}" + url[start + len(value):]
                
                patterns.append(PatternMatch(
                    pattern_type=pattern_type,
                    original_value=value,
                    position=start,
                    regex=regex.pattern,
                    template=template,
                ))
        
        return patterns
    
    def generate_fuzz_urls(
        self,
        url: str,
        max_per_pattern: int = 20,
    ) -> list[str]:
        """Generate all fuzz URLs for a given URL."""
        patterns = self.analyze(url)
        fuzz_urls = set()
        
        for pattern in patterns:
            variants = pattern.generate_variants(max_per_pattern)
            for variant in variants:
                fuzz_url = pattern.template.replace("{value}", variant)
                if fuzz_url != url:
                    fuzz_urls.add(fuzz_url)
        
        return list(fuzz_urls)


@dataclass
class FuzzResult:
    """Result of a fuzz attempt."""
    
    url: str
    status_code: int
    content_type: str | None
    content_length: int
    discovered: bool
    latency_ms: float
    pattern_type: str
    original_url: str


class PatternFuzzer:
    """Recursive fuzzer for discovering unindexed resources."""
    
    def __init__(
        self,
        max_concurrent: int = 10,
        timeout: float = 10.0,
        user_agent: str | None = None,
    ) -> None:
        self._max_concurrent = max_concurrent
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._analyzer = URLPatternAnalyzer()
        self._telemetry = get_telemetry()
        
        settings = get_settings()
        self._user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        )
        
        # Track discovered URLs to avoid duplicates
        self._discovered: set[str] = set()
        self._fuzzed: set[str] = set()
        
        logger.info(
            "pattern_fuzzer_initialized",
            max_concurrent=max_concurrent,
        )
    
    async def _check_url(
        self,
        url: str,
        pattern_type: str,
        original_url: str,
    ) -> FuzzResult | None:
        """Check if a URL exists and return result."""
        if url in self._fuzzed:
            return None
        
        self._fuzzed.add(url)
        
        async with self._semaphore:
            import time
            start = time.perf_counter()
            
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=True,
                ) as client:
                    response = await client.head(
                        url,
                        headers={"User-Agent": self._user_agent},
                    )
                    
                    latency_ms = (time.perf_counter() - start) * 1000
                    
                    # Consider 200, 301, 302 as discovered
                    discovered = response.status_code in [200, 301, 302]
                    
                    result = FuzzResult(
                        url=url,
                        status_code=response.status_code,
                        content_type=response.headers.get("content-type"),
                        content_length=int(response.headers.get("content-length", 0)),
                        discovered=discovered,
                        latency_ms=latency_ms,
                        pattern_type=pattern_type,
                        original_url=original_url,
                    )
                    
                    if discovered:
                        self._discovered.add(url)
                        logger.info(
                            "url_discovered",
                            url=url,
                            pattern_type=pattern_type,
                            status=response.status_code,
                        )
                    
                    return result
                    
            except httpx.HTTPError as e:
                logger.debug("fuzz_request_failed", url=url, error=str(e))
                return FuzzResult(
                    url=url,
                    status_code=0,
                    content_type=None,
                    content_length=0,
                    discovered=False,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    pattern_type=pattern_type,
                    original_url=original_url,
                )
    
    async def fuzz_url(
        self,
        url: str,
        max_variants: int = 20,
        recursive_depth: int = 1,
    ) -> list[FuzzResult]:
        """Fuzz a URL and return discovered resources.
        
        Args:
            url: The original URL to fuzz
            max_variants: Maximum variants per pattern
            recursive_depth: How deep to recursively fuzz discoveries
        """
        trace_id = create_trace_id()
        
        logger.info(
            "fuzzing_started",
            trace_id=trace_id,
            url=url,
            max_variants=max_variants,
            depth=recursive_depth,
        )
        
        # Analyze patterns
        patterns = self._analyzer.analyze(url)
        
        if not patterns:
            logger.info("no_patterns_found", url=url)
            return []
        
        logger.info(
            "patterns_detected",
            url=url,
            patterns=[p.pattern_type for p in patterns],
        )
        
        # Generate and check fuzz URLs
        all_results: list[FuzzResult] = []
        
        for pattern in patterns:
            variants = pattern.generate_variants(max_variants)
            tasks = []
            
            for variant in variants:
                fuzz_url = pattern.template.replace("{value}", variant)
                if fuzz_url != url and fuzz_url not in self._fuzzed:
                    tasks.append(
                        self._check_url(fuzz_url, pattern.pattern_type, url)
                    )
            
            if tasks:
                results = await asyncio.gather(*tasks)
                valid_results = [r for r in results if r is not None]
                all_results.extend(valid_results)
        
        # Recursive fuzzing on discoveries
        if recursive_depth > 0:
            discoveries = [r.url for r in all_results if r.discovered]
            
            for discovered_url in discoveries[:5]:  # Limit recursive depth
                recursive_results = await self.fuzz_url(
                    discovered_url,
                    max_variants=max_variants // 2,
                    recursive_depth=recursive_depth - 1,
                )
                all_results.extend(recursive_results)
        
        logger.info(
            "fuzzing_complete",
            trace_id=trace_id,
            url=url,
            total_checked=len(all_results),
            discovered=len([r for r in all_results if r.discovered]),
        )
        
        return all_results
    
    async def fuzz_batch(
        self,
        urls: list[str],
        max_variants: int = 20,
    ) -> dict[str, list[FuzzResult]]:
        """Fuzz multiple URLs."""
        results = {}
        
        for url in urls:
            results[url] = await self.fuzz_url(url, max_variants)
        
        return results
    
    def get_discoveries(self) -> list[str]:
        """Get all discovered URLs."""
        return list(self._discovered)
    
    async def download_discoveries(
        self,
        max_size_mb: int = 50,
    ) -> list[MinedRecord]:
        """Download all discovered resources and convert to MinedRecords."""
        records = []
        max_size_bytes = max_size_mb * 1024 * 1024
        
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            for url in self._discovered:
                try:
                    response = await client.get(
                        url,
                        headers={"User-Agent": self._user_agent},
                    )
                    
                    if response.status_code != 200:
                        continue
                    
                    content = response.content
                    
                    if len(content) > max_size_bytes:
                        logger.warning(
                            "content_too_large",
                            url=url,
                            size=len(content),
                        )
                        continue
                    
                    content_hash = MinedRecord.compute_content_hash(content)
                    parsed = urlparse(url)
                    
                    provenance = SourceProvenance(
                        url=url,
                        domain=parsed.netloc,
                        discovery_method="pattern_fuzzing",
                        retrieval_tier=FallbackTier.SHADOW_API,
                    )
                    
                    record = MinedRecord(
                        source_provenance=provenance,
                        content_hash=content_hash,
                        content_type=response.headers.get("content-type", "application/octet-stream"),
                        content=content,
                        content_size_bytes=len(content),
                        metadata={
                            "status_code": response.status_code,
                            "headers": dict(response.headers),
                        },
                    )
                    records.append(record)
                    
                except Exception as e:
                    logger.error("download_failed", url=url, error=str(e))
        
        logger.info("downloads_complete", count=len(records))
        return records


class DocumentPatternFuzzer(PatternFuzzer):
    """Specialized fuzzer for document patterns (PDFs, reports, etc.)."""
    
    DOCUMENT_PATTERNS = [
        # Annual reports
        ("annual_report_{year}.pdf", range(2015, 2027)),
        ("annual-report-{year}.pdf", range(2015, 2027)),
        ("{year}_annual_report.pdf", range(2015, 2027)),
        
        # Quarterly reports
        ("{year}Q{quarter}_report.pdf", [(y, q) for y in range(2020, 2027) for q in range(1, 5)]),
        ("Q{quarter}_{year}_report.pdf", [(q, y) for y in range(2020, 2027) for q in range(1, 5)]),
        
        # 10-K and 10-Q filings
        ("10K_{year}.pdf", range(2015, 2027)),
        ("10Q_Q{quarter}_{year}.pdf", [(q, y) for y in range(2020, 2027) for q in range(1, 5)]),
        
        # Internal documents
        ("internal_audit_{year}.pdf", range(2018, 2027)),
        ("budget_{year}.xlsx", range(2018, 2027)),
        ("forecast_{year}.xlsx", range(2018, 2027)),
    ]
    
    async def fuzz_documents(
        self,
        base_url: str,
        paths: list[str] | None = None,
    ) -> list[FuzzResult]:
        """Fuzz common document patterns on a base URL."""
        if paths is None:
            paths = [
                "/documents/",
                "/reports/",
                "/files/",
                "/assets/",
                "/downloads/",
                "/public/",
                "/investor-relations/",
                "/ir/",
            ]
        
        all_results = []
        
        for path in paths:
            for pattern, values in self.DOCUMENT_PATTERNS:
                for value in values:
                    if isinstance(value, tuple):
                        filename = pattern.format(
                            year=value[0] if "year" in pattern else value[1],
                            quarter=value[1] if len(value) > 1 else 1,
                        )
                    else:
                        filename = pattern.format(year=value, quarter=1)
                    
                    url = urljoin(base_url, f"{path}{filename}")
                    result = await self._check_url(url, "document_pattern", base_url)
                    
                    if result:
                        all_results.append(result)
        
        return all_results
