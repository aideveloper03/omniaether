"""Cloud Bucket Sniffer for AETHER-MINE.

Discovers public cloud storage buckets by:
- Generating brand name permutations
- Checking AWS S3, Azure Blobs, and Google Cloud Storage
- Enumerating accessible objects
"""

import asyncio
import itertools
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from src.core.models import (
    CloudBucketTarget,
    MinedRecord,
    SourceProvenance,
    FallbackTier,
)
from src.core.telemetry import get_telemetry, create_trace_id


logger = structlog.get_logger(__name__)


@dataclass
class BucketCheckResult:
    """Result of a bucket existence check."""
    
    bucket_name: str
    provider: str
    url: str
    exists: bool
    is_public: bool
    status_code: int
    error: str | None = None
    objects_found: int = 0
    sample_objects: list[str] = field(default_factory=list)


@dataclass
class CloudObject:
    """A discovered object in a cloud bucket."""
    
    bucket: str
    key: str
    provider: str
    url: str
    size: int | None = None
    last_modified: datetime | None = None
    content_type: str | None = None


class BrandPermutationGenerator:
    """Generates permutations of brand names for bucket discovery."""
    
    COMMON_SUFFIXES = [
        "", "-dev", "-prod", "-staging", "-test", "-backup",
        "-data", "-assets", "-static", "-media", "-files",
        "-public", "-private", "-internal", "-external",
        "-web", "-app", "-api", "-cdn", "-storage",
        "-archive", "-logs", "-reports", "-docs",
        "dev", "prod", "staging", "test", "backup",
    ]
    
    COMMON_PREFIXES = [
        "", "dev-", "prod-", "staging-", "test-",
        "backup-", "data-", "assets-", "static-",
    ]
    
    SEPARATORS = ["", "-", "_", "."]
    
    def __init__(self, brand_name: str) -> None:
        self._brand = self._normalize_brand(brand_name)
        self._variations = self._generate_brand_variations()
    
    def _normalize_brand(self, name: str) -> str:
        """Normalize brand name for bucket naming."""
        # Remove special characters, lowercase
        normalized = re.sub(r"[^a-zA-Z0-9\s-]", "", name.lower())
        # Replace spaces with hyphens
        normalized = re.sub(r"\s+", "-", normalized)
        return normalized
    
    def _generate_brand_variations(self) -> list[str]:
        """Generate variations of the brand name."""
        variations = [self._brand]
        
        # Add variations without hyphens
        variations.append(self._brand.replace("-", ""))
        
        # Add abbreviated versions
        words = self._brand.split("-")
        if len(words) > 1:
            # Initials
            variations.append("".join(w[0] for w in words))
            # First word only
            variations.append(words[0])
            # First two words
            if len(words) > 2:
                variations.append("-".join(words[:2]))
        
        return list(set(variations))
    
    def generate_permutations(self, max_count: int = 500) -> list[str]:
        """Generate all bucket name permutations."""
        permutations = set()
        
        for variation in self._variations:
            # Basic variation
            permutations.add(variation)
            
            # With suffixes
            for suffix in self.COMMON_SUFFIXES:
                for sep in self.SEPARATORS:
                    if suffix:
                        permutations.add(f"{variation}{sep}{suffix}")
            
            # With prefixes
            for prefix in self.COMMON_PREFIXES:
                if prefix:
                    permutations.add(f"{prefix}{variation}")
            
            # Common cloud patterns
            permutations.add(f"{variation}-s3")
            permutations.add(f"{variation}-bucket")
            permutations.add(f"{variation}-cloud")
            permutations.add(f"s3-{variation}")
            permutations.add(f"bucket-{variation}")
        
        # Filter valid bucket names
        valid = [
            p for p in permutations
            if self._is_valid_bucket_name(p)
        ]
        
        return list(valid)[:max_count]
    
    def _is_valid_bucket_name(self, name: str) -> bool:
        """Check if bucket name is valid for cloud providers."""
        # Length check (3-63 for most providers)
        if not (3 <= len(name) <= 63):
            return False
        
        # Must start and end with alphanumeric
        if not (name[0].isalnum() and name[-1].isalnum()):
            return False
        
        # No consecutive dots or hyphens
        if ".." in name or "--" in name:
            return False
        
        # Only lowercase letters, numbers, hyphens, dots
        if not re.match(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$", name):
            return False
        
        return True


class CloudBucketSniffer:
    """Discovers and enumerates public cloud buckets."""
    
    # Cloud provider URL patterns
    PROVIDERS = {
        "aws": {
            "url_patterns": [
                "https://{bucket}.s3.amazonaws.com",
                "https://{bucket}.s3.{region}.amazonaws.com",
                "https://s3.amazonaws.com/{bucket}",
                "https://s3.{region}.amazonaws.com/{bucket}",
            ],
            "regions": [
                "us-east-1", "us-east-2", "us-west-1", "us-west-2",
                "eu-west-1", "eu-west-2", "eu-central-1",
                "ap-southeast-1", "ap-southeast-2", "ap-northeast-1",
            ],
            "list_endpoint": "?list-type=2&max-keys=100",
        },
        "azure": {
            "url_patterns": [
                "https://{bucket}.blob.core.windows.net",
            ],
            "regions": [],
            "list_endpoint": "?restype=container&comp=list&maxresults=100",
        },
        "gcp": {
            "url_patterns": [
                "https://storage.googleapis.com/{bucket}",
                "https://{bucket}.storage.googleapis.com",
            ],
            "regions": [],
            "list_endpoint": "?max-keys=100",
        },
    }
    
    def __init__(
        self,
        max_concurrent: int = 20,
        timeout: float = 10.0,
    ) -> None:
        self._max_concurrent = max_concurrent
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._telemetry = get_telemetry()
        
        self._discovered_buckets: list[BucketCheckResult] = []
        self._public_buckets: list[BucketCheckResult] = []
        
        logger.info(
            "cloud_sniffer_initialized",
            max_concurrent=max_concurrent,
        )
    
    async def _check_bucket(
        self,
        bucket_name: str,
        provider: str,
        url: str,
    ) -> BucketCheckResult:
        """Check if a bucket exists and is accessible."""
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=True,
                ) as client:
                    # HEAD request to check existence
                    response = await client.head(url)
                    
                    exists = response.status_code not in [404, 400]
                    is_public = response.status_code == 200
                    
                    result = BucketCheckResult(
                        bucket_name=bucket_name,
                        provider=provider,
                        url=url,
                        exists=exists,
                        is_public=is_public,
                        status_code=response.status_code,
                    )
                    
                    # If public, try to list objects
                    if is_public:
                        objects = await self._list_objects(client, bucket_name, provider, url)
                        result.objects_found = len(objects)
                        result.sample_objects = [o.key for o in objects[:10]]
                        
                        logger.info(
                            "public_bucket_found",
                            bucket=bucket_name,
                            provider=provider,
                            objects=result.objects_found,
                        )
                        
                        self._public_buckets.append(result)
                    
                    if exists:
                        self._discovered_buckets.append(result)
                    
                    return result
                    
            except httpx.HTTPError as e:
                return BucketCheckResult(
                    bucket_name=bucket_name,
                    provider=provider,
                    url=url,
                    exists=False,
                    is_public=False,
                    status_code=0,
                    error=str(e),
                )
    
    async def _list_objects(
        self,
        client: httpx.AsyncClient,
        bucket_name: str,
        provider: str,
        base_url: str,
    ) -> list[CloudObject]:
        """List objects in a bucket."""
        objects = []
        
        try:
            list_endpoint = self.PROVIDERS[provider]["list_endpoint"]
            list_url = f"{base_url}{list_endpoint}"
            
            response = await client.get(list_url)
            
            if response.status_code != 200:
                return objects
            
            content = response.text
            
            # Parse XML response (common for all providers)
            # AWS S3 / GCS format
            keys = re.findall(r"<Key>([^<]+)</Key>", content)
            sizes = re.findall(r"<Size>(\d+)</Size>", content)
            
            for i, key in enumerate(keys):
                size = int(sizes[i]) if i < len(sizes) else None
                
                obj = CloudObject(
                    bucket=bucket_name,
                    key=key,
                    provider=provider,
                    url=f"{base_url}/{key}",
                    size=size,
                )
                objects.append(obj)
            
            # Azure Blob format
            if provider == "azure":
                blob_names = re.findall(r"<Name>([^<]+)</Name>", content)
                for name in blob_names:
                    obj = CloudObject(
                        bucket=bucket_name,
                        key=name,
                        provider=provider,
                        url=f"{base_url}/{name}",
                    )
                    objects.append(obj)
                    
        except Exception as e:
            logger.debug("list_objects_failed", bucket=bucket_name, error=str(e))
        
        return objects
    
    async def sniff_brand(
        self,
        brand_name: str,
        providers: list[str] | None = None,
        max_permutations: int = 200,
    ) -> list[BucketCheckResult]:
        """Scan for buckets related to a brand name."""
        trace_id = create_trace_id()
        
        if providers is None:
            providers = ["aws", "azure", "gcp"]
        
        generator = BrandPermutationGenerator(brand_name)
        permutations = generator.generate_permutations(max_permutations)
        
        logger.info(
            "sniffing_started",
            trace_id=trace_id,
            brand=brand_name,
            permutations=len(permutations),
            providers=providers,
        )
        
        tasks = []
        
        for bucket_name in permutations:
            for provider in providers:
                provider_config = self.PROVIDERS[provider]
                
                for url_pattern in provider_config["url_patterns"]:
                    regions = provider_config["regions"] or [None]
                    
                    for region in regions:
                        if region:
                            url = url_pattern.format(bucket=bucket_name, region=region)
                        else:
                            if "{region}" in url_pattern:
                                continue
                            url = url_pattern.format(bucket=bucket_name)
                        
                        tasks.append(
                            self._check_bucket(bucket_name, provider, url)
                        )
        
        # Execute with rate limiting
        results = []
        batch_size = 50
        
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, BucketCheckResult):
                    results.append(result)
            
            # Small delay between batches
            await asyncio.sleep(0.5)
        
        discovered = [r for r in results if r.exists]
        public = [r for r in results if r.is_public]
        
        logger.info(
            "sniffing_complete",
            trace_id=trace_id,
            brand=brand_name,
            total_checked=len(results),
            discovered=len(discovered),
            public=len(public),
        )
        
        return results
    
    async def enumerate_bucket(
        self,
        bucket_url: str,
        provider: str | None = None,
        max_objects: int = 1000,
    ) -> list[CloudObject]:
        """Enumerate all objects in a bucket."""
        if provider is None:
            # Detect provider from URL
            if "s3.amazonaws.com" in bucket_url:
                provider = "aws"
            elif "blob.core.windows.net" in bucket_url:
                provider = "azure"
            elif "storage.googleapis.com" in bucket_url:
                provider = "gcp"
            else:
                provider = "aws"  # Default
        
        parsed = urlparse(bucket_url)
        bucket_name = parsed.netloc.split(".")[0]
        
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            objects = await self._list_objects(
                client,
                bucket_name,
                provider,
                bucket_url,
            )
        
        return objects[:max_objects]
    
    async def download_objects(
        self,
        objects: list[CloudObject],
        max_size_mb: int = 50,
    ) -> list[MinedRecord]:
        """Download objects and convert to MinedRecords."""
        records = []
        max_size = max_size_mb * 1024 * 1024
        
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            for obj in objects:
                try:
                    # Skip large files
                    if obj.size and obj.size > max_size:
                        logger.debug("skipping_large_file", url=obj.url, size=obj.size)
                        continue
                    
                    response = await client.get(obj.url)
                    
                    if response.status_code != 200:
                        continue
                    
                    content = response.content
                    
                    if len(content) > max_size:
                        continue
                    
                    content_hash = MinedRecord.compute_content_hash(content)
                    
                    provenance = SourceProvenance(
                        url=obj.url,
                        domain=f"{obj.bucket}.{obj.provider}",
                        discovery_method="cloud_bucket_sniffing",
                        retrieval_tier=FallbackTier.SHADOW_API,
                    )
                    
                    record = MinedRecord(
                        source_provenance=provenance,
                        content_hash=content_hash,
                        content_type=response.headers.get(
                            "content-type",
                            "application/octet-stream",
                        ),
                        content=content,
                        content_size_bytes=len(content),
                        metadata={
                            "bucket": obj.bucket,
                            "key": obj.key,
                            "provider": obj.provider,
                        },
                    )
                    records.append(record)
                    
                except Exception as e:
                    logger.error("download_failed", url=obj.url, error=str(e))
        
        return records
    
    def get_public_buckets(self) -> list[BucketCheckResult]:
        """Get all discovered public buckets."""
        return list(self._public_buckets)
    
    def get_discovered_buckets(self) -> list[BucketCheckResult]:
        """Get all discovered buckets (including non-public)."""
        return list(self._discovered_buckets)
