import asyncio
from typing import List
from loguru import logger
from src.core.evasion import EvasionProfile
from src.storage.models import DocumentRecord, compute_content_hash
from src.storage.parquet_stream import stream_writer
from src.core.telemetry import get_trace_id
from datetime import datetime

class CloudBucketSniffer:
    def __init__(self):
        self.session = EvasionProfile.create_stealth_session()
        self.platforms = {
            "aws": "https://{}.s3.amazonaws.com",
            "gcp": "https://storage.googleapis.com/{}",
            "azure": "https://{}.blob.core.windows.net/container" # Simplified
        }

    async def sniff_brand(self, brand_name: str):
        """
        Generate permutations and check cloud storage buckets.
        """
        permutations = self._generate_permutations(brand_name)
        
        tasks = []
        for name in permutations:
            for platform, url_template in self.platforms.items():
                target_url = url_template.format(name)
                tasks.append(self._check_bucket(target_url, platform))
        
        # Run in batches to avoid rate limits
        # Simple loop for demo
        for task in tasks:
            await task

    def _generate_permutations(self, brand: str) -> List[str]:
        base = brand.lower().replace(" ", "")
        perms = [
            base,
            f"{base}-assets",
            f"{base}-public",
            f"{base}-internal",
            f"{base}-data",
            f"{base}-backups",
            f"dev-{base}",
            f"staging-{base}"
        ]
        return perms

    async def _check_bucket(self, url: str, platform: str):
        try:
            # Check for XML listing (public bucket)
            response = self.session.get(url, timeout=5)
            
            if response.status_code == 200 and ("<ListBucketResult>" in response.text or "<Error>" not in response.text):
                logger.info(f"Open Cloud Bucket Discovered: {url} ({platform})")
                
                record = DocumentRecord(
                    timestamp=datetime.utcnow(),
                    source_provenance=url,
                    content_hash=compute_content_hash(url), # Just hash URL for bucket discovery
                    trace_id=get_trace_id(),
                    file_name="BUCKET_ROOT",
                    file_type="xml/bucket-listing",
                    file_size_bytes=len(response.content),
                    s3_bucket=url,
                    text_content=response.text[:1000], # First 1k chars
                    metadata={"platform": platform, "status": "OPEN"}
                )
                stream_writer.add_record(record)
                
        except Exception:
            pass
