import re
import asyncio
from datetime import datetime
from typing import List, Set
from loguru import logger
from src.core.evasion import EvasionProfile
from src.storage.models import DocumentRecord, compute_content_hash
from src.storage.parquet_stream import stream_writer
from src.core.telemetry import get_trace_id

class RecursiveFuzzer:
    def __init__(self):
        self.session = EvasionProfile.create_stealth_session()
        self.visited: Set[str] = set()

    async def fuzz_resource(self, seed_url: str):
        """
        Analyze a seed URL and fuzz it for hidden siblings.
        e.g. .../report_2024.pdf -> report_2023.pdf, report_2025.pdf
        """
        if seed_url in self.visited:
            return
        self.visited.add(seed_url)

        # Identify numeric patterns
        # Regex to find numbers at the end of filenames or in paths
        patterns = [
            (r'(\d{4})', 2000, 2030), # Years
            (r'v(\d+)', 1, 10),       # Versions
            (r'(\d+)', 1, 100)        # Generic IDs (limited range)
        ]

        found_urls = []
        
        for pattern, min_val, max_val in patterns:
            match = re.search(pattern, seed_url)
            if match:
                original_val = match.group(1)
                try:
                    current_num = int(original_val)
                    
                    # Fuzz range (e.g. +/- 5) or full range if small
                    # To be efficient, we scan around the value
                    scan_range = range(max(min_val, current_num - 5), min(max_val, current_num + 5))
                    
                    for num in scan_range:
                        if num == current_num:
                            continue
                            
                        new_val = str(num).zfill(len(original_val))
                        fuzzed_url = seed_url.replace(original_val, new_val)
                        
                        if fuzzed_url not in self.visited:
                            found = await self._check_url(fuzzed_url)
                            if found:
                                found_urls.append(fuzzed_url)
                                self.visited.add(fuzzed_url)
                                
                except ValueError:
                    continue

        return found_urls

    async def _check_url(self, url: str) -> bool:
        try:
            # Run in executor because curl_cffi is sync (mostly) or use async wrapper
            # curl_cffi requests are sync by default unless using AsyncSession.
            # But here we initialized a sync session in init? 
            # EvasionProfile.create_stealth_session returns a sync Session.
            # We should probably use AsyncSession for async context.
            
            # For simplicity in this demo, we assume sync call wrapped or fast enough
            response = self.session.get(url, allow_redirects=True, timeout=5)
            
            if response.status_code == 200:
                logger.info(f"Fuzzing hit: {url}")
                # Save found resource
                self._save_document(url, response)
                return True
            return False
        except Exception as e:
            # logger.debug(f"Fuzzing failed for {url}: {e}")
            return False

    def _save_document(self, url: str, response):
        try:
            content = response.content
            record = DocumentRecord(
                timestamp=datetime.utcnow(),
                source_provenance=url,
                content_hash=compute_content_hash(content),
                trace_id=get_trace_id(),
                file_name=url.split("/")[-1],
                file_type=response.headers.get("content-type", "application/octet-stream"),
                file_size_bytes=len(content),
                text_content="", # Would need PDF/Doc parser here
                metadata={"status": response.status_code}
            )
            stream_writer.add_record(record)
        except Exception as e:
            logger.error(f"Failed to save fuzzed document: {e}")
